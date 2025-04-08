from langchain.chains import RetrievalQA
from langchain_community.chat_models import ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.text_splitter import CharacterTextSplitter
import os, glob

vectorstore = None

class MemoryEngine:
    def __init__(self):
        global vectorstore

        script_path = "calls/script/*.txt"
        self.script_sections = {}
        for path in sorted(glob.glob(script_path)):
            key = os.path.basename(path).replace(".txt", "")
            with open(path, "r") as file:
                content = file.read()
                self.script_sections[key] = [part.strip() for part in content.split("[gather]") if part.strip()]

        self.known_objections = self._load_known_objections("calls/script/objections.txt")

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
        self.precomputed_objection_embeddings = {
            key: self.embedding_model.embed_query(key)
            for key in self.known_objections
        }

    def reset_script(self, call_sid):
        flat_script = []
        for section in self.script_sections.values():
            flat_script.extend(section)

        self.call_memory[call_sid] = {
            "script_segments": flat_script,
            "current_index": 0,
            "in_objection_followup": False,
            "pending_followup": None
        }

    def generate_response(self, call_sid, user_input):
        memory = self.call_memory.get(call_sid)
        if not memory:
            return {"response": "Let’s go ahead and keep moving — this part will get cleared up during your consultation."}

        if user_input == "initial":
            if memory["script_segments"]:
                memory["current_index"] = 1
                return {"response": memory["script_segments"][0], "sources": ["script"]}

        if memory.get("in_objection_followup") and memory.get("pending_followup"):
            followup = memory.pop("pending_followup")
            memory["in_objection_followup"] = False
            return {"response": followup.strip(), "sources": ["followup"]}

        if memory.get("in_objection_followup"):
            memory["in_objection_followup"] = False
            return self._next_script_line(memory)

        # ✅ Detect objections
        matched_key = self._exact_match_objection(user_input)
        if not matched_key:
            matched_key = self._semantic_match_objection(user_input)

        if matched_key:
            objection_data = self.known_objections[matched_key]
            memory["in_objection_followup"] = True
            memory["pending_followup"] = objection_data.get("followup", "")
            return {"response": objection_data["response"], "sources": ["memory"]}

        # ✅ Short/neutral/unclear input — skip QA and just move on
        vague = [
            "yeah", "yes", "sure", "i guess", "i think so", "that’s right", "correct",
            "uh huh", "yep", "ya", "i own it", "not sure", "i don’t know", "i don't know",
            "maybe", "probably", "okay", "alright", "hello", "hi", "huh", "what"
        ]
        if len(user_input.strip()) < 12 or any(p in user_input.lower() for p in vague):
            return self._next_script_line(memory)

        # ✅ Attempt fallback QA
        try:
            answer = self.qa.run(user_input)
            cleaned = answer.strip().lower()
            fallback_phrases = [
                "how can i assist you", "how can i help you", "i don't know",
                "i’m sorry", "not sure", "sorry", "that's a good question"
            ]
            if len(cleaned) < 12 or any(p in cleaned for p in fallback_phrases + vague):
                return self._next_script_line(memory)
            return {"response": answer.strip(), "sources": ["memory"]}
        except Exception as e:
            print("[⚠️ QA fallback error]", str(e))
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

        return {
            "response": "Let’s go ahead and keep moving — this part will get cleared up during your consultation.",
            "sources": ["memory"]
        }

    def _load_known_objections(self, path):
        objections = {}
        with open(path, "r") as file:
            lines = file.readlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("[objection]"):
                i += 1
                if i < len(lines):
                    key = lines[i].strip().lower()
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
                    objections[key.lower()] = {
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
