from langchain.chains import RetrievalQA
from langchain_community.chat_models import ChatOpenAI
from langchain.vectorstores import Chroma
from langchain.document_loaders import TextLoader
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.text_splitter import CharacterTextSplitter
import os
import glob

# Shared vectorstore for external tools
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

        # Memory state for each caller
        self.call_memory = {}

        # Fallback knowledge base (for objections or questions)
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

        # Initial script start
        if user_input == "initial":
            if memory["script_segments"]:
                next_line = memory["script_segments"][0]
                memory["current_index"] = 1
                return {"response": next_line.strip(), "sources": ["script"]}

        # Move through script
        if memory["current_index"] < len(memory["script_segments"]):
            next_line = memory["script_segments"][memory["current_index"]]
            memory["current_index"] += 1
            return {"response": next_line.strip(), "sources": ["script"]}

        # Fallback to QA (objection handling)
        try:
            answer = self.qa.run(user_input)
            cleaned = self._clean(answer)
            return {
                "response": cleaned,
                "sources": ["memory"]
            }
        except Exception as e:
            print("[⚠️ QA fallback error]", str(e))
            return {
                "response": "Good question — we’ll go over that during your consultation.",
                "sources": ["memory"]
            }

    def _clean(self, text):
        return text.replace("[objection]", "").replace("[response]", "").strip()
