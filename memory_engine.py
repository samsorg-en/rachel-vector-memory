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

        # ✅ Objections KB
        loader = TextLoader("calls/script/objections.txt")
        docs = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=400, chunk_overlap=0)
        texts = text_splitter.split_documents(docs)
        embedding = OpenAIEmbeddings()
        vectorstore = Chroma.from_documents(texts, embedding)

        retriever = vectorstore.as_retriever(search_kwargs={"k": 2})
        self.qa = RetrievalQA.from_chain_type(
            llm=ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7, request_timeout=8, max_tokens=256),
            retriever=retriever
        )

        self.call_memory = {}
        self.embedding_model = embedding
        self.known_objections = self._load_known_objections("calls/script/objections.txt")

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

        # ✅ Start of call
        if user_input == "initial":
            if memory["script_segments"]:
                next_line = memory["script_segments"][0]
                memory["current_index"] = 1
                return {"response": next_line.strip(), "sources": ["script"]}

        # ✅ Objection follow-up if queued
        if memory.get("in_objection_followup") and memory.get("pending_followup"):
            followup = memory.pop("pending_followup")
            memory["in_objection_followup"] = False
            return {"response": followup.strip(), "sources": ["followup"]}

        # ✅ Continue script after follow-up
        if memory.get("in_objection_followup"):
            memory["in_objection_followup"] = False
            if memory["current_index"] < len(memory["script_segments"]):
                next_line = memory["script_segments"][memory["current_index"]]
                memory["current_index"] += 1
                return {"response": next_line.strip(), "sources": ["script"]}

        # ✅ Detect and respond to objection
        matched_key = self._semantic_match_objection(user_input)
        if matched_key:
            response_data = self.known_objections[matched_key]
            memory["in_objection_followup"] = True
            memory["pending_followup"] = response_data.get("followup", "")
            return {"response": response_data["response"].strip(), "sources": ["memory"]}

        # ✅ Continue script
        if memory["current_index"] < len(memory["script_segments"]):
            next_line = memory["script_segments"][memory["current_index"]]
            memory["current_index"] += 1
            return {"response": next_line.strip(), "sources": ["script"]}

        # ✅ Fallback QA
        try:
            answer = self.qa.run(user_input)
            return {"response": answer.strip(), "sources": ["memory"]}
        except Exception as e:
            print("[⚠️ QA fallback error]", str(e))
            return {"response": "Good question — we’ll go over that during your consultation.", "sources": ["memory"]}

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
                    response = ""
                    followup = ""
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
                    objections[key] = {
                        "response": response.strip(),
                        "followup": followup.strip()
                    }
            else:
                i += 1
        return objections

    def _semantic_match_objection(self, user_input, threshold=0.82):
        user_embedding = self.embedding_model.embed_query(user_input)
        highest_score = 0
        best_match = None

        for objection_text in self.known_objections:
            objection_embedding = self.embedding_model.embed_query(objection_text)
            score = self._cosine_similarity(user_embedding, objection_embedding)

            if score > highest_score:
                highest_score = score
                best_match = objection_text

        if highest_score >= threshold:
            return best_match
        return None

    def _cosine_similarity(self, vec1, vec2):
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        return dot / (norm1 * norm2)
