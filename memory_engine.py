from langchain.chains import RetrievalQA
from langchain_community.chat_models import ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.text_splitter import CharacterTextSplitter
import os
import glob

vectorstore = None

class MemoryEngine:
    def __init__(self):
        global vectorstore

        # ✅ Load structured script
        script_path = "calls/script/*.txt"
        self.script_sections = {}
        for path in sorted(glob.glob(script_path)):
            key = os.path.basename(path).replace(".txt", "")
            with open(path, "r") as file:
                content = file.read()
                self.script_sections[key] = [part.strip() for part in content.split("[gather]") if part.strip()]

        # ✅ Load objection knowledge base
        loader = TextLoader("calls/script/objections.txt")
        docs = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=400, chunk_overlap=0)
        texts = text_splitter.split_documents(docs)
        embedding = OpenAIEmbeddings()
        vectorstore = Chroma.from_documents(texts, embedding)

        retriever = vectorstore.as_retriever(search_kwargs={"k": 2})
        self.qa = RetrievalQA.from_chain_type(
            llm=ChatOpenAI(
                model="gpt-3.5-turbo",
                temperature=0.7,
                request_timeout=8,
                max_tokens=256
            ),
            retriever=retriever
        )

        # ✅ Runtime session memory
        self.call_memory = {}
        self.known_objections = self._load_known_objections("calls/script/objections.txt")

    def reset_script(self, call_sid):
        flat_script = []
        for section in self.script_sections.values():
            flat_script.extend(section)

        self.call_memory[call_sid] = {
            "script_segments": flat_script,
            "current_index": 0
        }

    def generate_response(self, call_sid, user_input):
        memory = self.call_memory.get(call_sid)
        if not memory:
            return {"response": "Sorry, something went wrong."}

        # ✅ Script intro
        if user_input == "initial":
            if memory["script_segments"]:
                next_line = memory["script_segments"][0]
                memory["current_index"] = 1
                return {"response": next_line.strip(), "sources": ["script"]}

        # ✅ Objection matching override
        matched = self._match_objection(user_input)
        if matched:
            response = self.known_objections[matched]

            # Continue script AFTER handling objection
            next_line = None
            if memory["current_index"] < len(memory["script_segments"]):
                next_line = memory["script_segments"][memory["current_index"]]
                memory["current_index"] += 1

            combined_response = f"{response} {next_line.strip()}" if next_line else response
            return {
                "response": combined_response,
                "sources": ["memory"]
            }

        # ✅ Regular script progression
        if memory["current_index"] < len(memory["script_segments"]):
            next_line = memory["script_segments"][memory["current_index"]]
            memory["current_index"] += 1
            return {"response": next_line.strip(), "sources": ["script"]}

        # ✅ Fallback to QA
        try:
            answer = self.qa.run(user_input)
            return {
                "response": answer,
                "sources": ["memory"]
            }
        except Exception as e:
            print("[⚠️ QA fallback error]", str(e))
            return {
                "response": "Good question — we’ll go over that during your consultation.",
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
                    response = ""
                    if i < len(lines) and lines[i].strip().startswith("[response]"):
                        i += 1
                        while i < len(lines) and not lines[i].strip().startswith("[objection]"):
                            response += lines[i].strip() + " "
                            i += 1
                    objections[key] = response.strip()
            else:
                i += 1
        return objections

    def _match_objection(self, user_input):
        user_input = user_input.lower()
        for objection in self.known_objections:
            if objection in user_input or user_input in objection:
                return objection
        return None
