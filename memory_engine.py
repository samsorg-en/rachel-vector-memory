from langchain.chains import RetrievalQA
from langchain_community.chat_models import ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.text_splitter import CharacterTextSplitter
import os, glob

vectorstore = None

class MemoryEngine:
    def __init__(self, synthesize_fn=None):
        global vectorstore

        # ✅ Inject synthesize function from app.py
        self.synthesize = synthesize_fn

        # ✅ Load script
        script_path = "calls/script/*.txt"
        self.script_sections = {}
        for path in sorted(glob.glob(script_path)):
            key = os.path.basename(path).replace(".txt", "")
            with open(path, "r") as file:
                content = file.read()
                self.script_sections[key] = [part.strip() for part in content.split("[gather]") if part.strip()]

        # ✅ Objection memory
        self.known_objections = self._load_known_objections("calls/script/objections.txt")

        # ✅ Setup vector QA fallback
        loader = TextLoader("calls/script/objections.txt")
        docs = loader.load()
        splitter = CharacterTextSplitter(chunk_size=400, chunk_overlap=0)
        texts = splitter.split_documents(docs)
        embedding = OpenAIEmbeddings()
        vectorstore = Chroma.from_documents(texts, embedding)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 2})
        self.qa = RetrievalQA.from_chain_type(
            llm=ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7, request_timeout=4, max_tokens=128),
            retriever=retriever
        )

        self.call_memory = {}
        self.embedding_model = embedding
        self.call_audio_cache = {}  # 🔥 New: cache of MP3s

        # ✅ Precompute objection embeddings
        self.precomputed_objection_embeddings = {
            key: self.embedding_model.embed_query(key)
            for key in self.known_objections
        }

        # ✅ Pre-synthesize & cache audio for all lines
        if self.synthesize:
            for section in self.script_sections.values():
                for line in section:
                    if line.strip():
                        self.call_audio_cache[line.strip()] = self.synthesize(line.strip())
            for key, data in self.known_objections.items():
                if data.get("response"):
                    self.call_audio_cache[data["response"]] = self.synthesize(data["response"])
                if data.get("followup"):
                    self.call_audio_cache[data["followup"]] = self.synthesize(data["followup"])

    def get_audio_url(self, text):
        return self.call_audio_cache.get(text.strip())

    def reset_script(self, call_sid):
        flat_script = []
        for section in self.script_sections.values():
            flat_script.extend(section)

        self.call_memory[call_sid] = {
            "script_segments": flat_script,
            "current_index": 0,
            "in_objection_followup": False,
            "pending_followup": None,
            "resume_index": None,
            "pending_followup_handled": False,
            "waiting_for_followup_reply": False
        }

    def generate_response(self, call_sid, user_input):
        if call_sid not in self.call_memory:
            self.reset_script(call_sid)

        memory = self.call_memory[call_sid]

        if user_input == "initial":
            if memory["script_segments"]:
                return self._next_script_line(memory)

        if memory.get("waiting_for_followup_reply"):
            followup = memory.get("pending_followup")
            if followup:
                print(f"[🔁 Delivering follow-up] {followup}")
                memory["waiting_for_followup_reply"] = False
                memory["pending_followup"] = None
                if memory.get("resume_index") is not None:
                    memory["current_index"] = memory.pop("resume_index")
                    print(f"[📍 Resuming script at index] {memory['current_index']}")
                else:
                    print("[⚠️ resume_index missing — defaulting to current position]")
                return {"response": followup.strip(), "sources": ["followup"]}

        # ✅ Safe replies that should never trigger objections
        safe_phrases = [
            "hello", "hi", "yes", "yeah", "yep", "this is", "who is this", "how can i help",
            "yes this is", "speaking", "it is", "you got em"
        ]
        for phrase in safe_phrases:
            if phrase in user_input.lower():
                return self._next_script_line(memory)

        matched_key = self._exact_match_objection(user_input)
        if not matched_key:
            matched_key = self._semantic_match_objection(user_input)

        if matched_key:
            objection_data = self.known_objections.get(matched_key, {})
            response_text = objection_data.get("response", "").strip()
            followup_text = objection_data.get("followup", "").strip()

            if not response_text:
                print(f"[⚠️ Empty objection response] for key: {matched_key}")
                return self._next_script_line(memory)

            memory["in_objection_followup"] = True
            memory["waiting_for_followup_reply"] = True
            memory["pending_followup"] = followup_text
            if memory["current_index"] + 1 < len(memory["script_segments"]):
                memory["resume_index"] = memory["current_index"] + 1
            else:
                memory["resume_index"] = len(memory["script_segments"])

            print(f"[✅ Objection matched] {matched_key} → {response_text}")
            return {"response": response_text, "sources": ["memory"]}

        vague_yes = [
            "yeah", "yes", "sure", "i guess", "i think so", "that’s right", "correct",
            "uh huh", "yep", "ya", "maybe", "probably", "okay", "alright"
        ]
        if user_input.lower().strip() in vague_yes:
            return self._next_script_line(memory)

        return self._next_script_line(memory)

    def _next_script_line(self, memory):
        try:
            if memory["current_index"] < len(memory["script_segments"]):
                line = memory["script_segments"][memory["current_index"]]
                memory["current_index"] += 1
                if line.strip():
                    return {"response": line.strip(), "sources": ["script"]}
        except Exception as e:
            print("[⚠️ Script progression error]", str(e))
        return {"response": "", "sources": ["script"]}

    def _load_known_objections(self, path):
        objections = {}
        with open(path, "r") as file:
            lines = file.readlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("[objection]"):
                i += 1
                keys = []
                while i < len(lines) and not lines[i].strip().startswith("[response]") and not lines[i].strip().startswith("[objection]"):
                    keys.append(lines[i].strip().lower())
                    i += 1
                response, followup = "", ""
                if i < len(lines) and lines[i].strip().startswith("[response]"):
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith("[followup]") and not lines[i].strip().startswith("[objection]"):
                        response += lines[i].strip() + " "
                        i += 1
                if i < len(lines) and lines[i].strip().startswith("[followup]"):
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith("[objection]"):
                        followup += lines[i].strip() + " "
                        i += 1
                for key in keys:
                    objections[key] = {
                        "response": response.strip(),
                        "followup": followup.strip()
                    }
            else:
                i += 1
        return objections

    def _exact_match_objection(self, user_input):
        for key in self.known_objections:
            if key in user_input.lower():
                return key
        return None

    def _semantic_match_objection(self, user_input, threshold=0.82):
        user_embedding = self.embedding_model.embed_query(user_input)
        best_score = 0
        best_key = None
        for key, cached_embedding in self.precomputed_objection_embeddings.items():
            score = self._cosine_similarity(user_embedding, cached_embedding)
            if score > best_score:
                best_score = score
                best_key = key
        return best_key if best_score >= threshold else None

    def _cosine_similarity(self, vec1, vec2):
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        return dot / (norm1 * norm2)
