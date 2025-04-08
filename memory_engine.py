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

        # ✅ Precompute objection embeddings
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
            return {"response": "Sorry, something went wrong."}

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
            if memory["current_index"] < len(memory["script_segments"]):
                line = memory["script_segments"][memory["current_index"]]
                memory["current_index"] += 1
                return {"response": line.strip(), "sources": ["script"]}

        matched_key = self._exact_match_objection(user_input)
        if matched_key:
            objection_data = self.known_objections[matched_key]
            memory["in_objection_followup"] = True
            memory["pending_followup"] = objection_data.get("followup", "")
            return {"response": objection_data["response"], "sources": ["memory"]}

        sem_key = self._semantic_match_objection(user_input)
        if sem_key:
            objection_data = self.known_objections[sem_key]
            memory["in_objection_followup"] = True
            memory["pending_followup"] = objection_data.get("followup", "")
            return {"response": objection_data["response"], "sources": ["memory"]}

        vague_confirmations = [
            "yeah", "yes", "sure", "i guess", "i think so",
            "that’s right", "correct", "uh huh", "yep", "ya", "i own it"
        ]

        try:
            answer = self.qa.run(user_input)
            cleaned = answer.strip().lower()
            if (
                not cleaned or
                cleaned.startswith("i don't know") or
                cleaned.startswith("i'm sorry") or
                "don't have enough context" in cleaned or
                len(cleaned) < 10 or
                any(phrase in cleaned for phrase in vague_confirmations)
            ):
                if memory["current_index"] < len(memory["script_segments"]):
                    line = memory["script_segments"][memory["current_index"]]
                    memory["current_index"] += 1
                    return {"response": line.strip(), "sources": ["script"]}
            return {"response": answer.strip(), "sources": ["memory"]}
        except Exception as e:
            print("[⚠️ QA fallback error]", str(e))
            if memory["current_index"] < len(memory["script_segments"]):
                line = memory["script_segments"][memory["current_index"]]
                memory["current_index"] += 1
                return {"response": line.strip(), "sources": ["script"]}
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
