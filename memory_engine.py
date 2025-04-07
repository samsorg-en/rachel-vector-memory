from langchain.chains import RetrievalQA
from langchain_community.chat_models import ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.text_splitter import CharacterTextSplitter
import os
import glob

class MemoryEngine:
    def __init__(self):
        script_path = "calls/script/*.txt"
        self.script_sections = {}
        for path in sorted(glob.glob(script_path)):
            key = os.path.basename(path).replace(".txt", "")
            with open(path, "r") as file:
                self.script_sections[key] = file.read()

        # Memory state for each caller
        self.call_memory = {}

        # Fallback knowledge base (for objections or questions)
        loader = TextLoader("calls/script/objections.txt")
        docs = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=400, chunk_overlap=0)
        texts = text_splitter.split_documents(docs)
        embedding = OpenAIEmbeddings()
        self.vectorstore = Chroma.from_documents(texts, embedding)

        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 2})
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
        self.call_memory[call_sid] = {
            "script_keys": list(self.script_sections.keys()),
            "current_index": 0
        }

    def generate_response(self, call_sid, user_input):
        memory = self.call_memory.get(call_sid)

        if not memory:
            return {"response": "Sorry, something went wrong."}

        # If first input, start script
        if user_input == "initial":
            next_line = self.script_sections[memory["script_keys"][0]]
            memory["current_index"] += 1
            return {
                "response": self._clean(next_line),
                "sources": ["script"]
            }

        # If still reading from script
        if memory["current_index"] < len(memory["script_keys"]):
            key = memory["script_keys"][memory["current_index"]]
            line = self.script_sections[key]
            memory["current_index"] += 1
            return {
                "response": self._clean(line),
                "sources": ["script"]
            }

        # Else fallback to QA
        answer = self.qa.run(user_input)
        return {
            "response": answer,
            "sources": ["memory"]
        }

    def _clean(self, text):
        return text.replace("[gather]", "").strip()
