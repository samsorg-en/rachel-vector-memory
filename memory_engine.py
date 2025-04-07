import os
from langchain.chains import RetrievalQA
from langchain_community.chat_models import ChatOpenAI
from langchain.vectorstores import Chroma
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.vectorstores import Chroma as ChromaDB

# ✅ Load the script files and split them
def load_script_chunks():
    loader = TextLoader("calls/script/intro.txt")  # Modify if more files are needed
    documents = loader.load()
    splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    return splitter.split_documents(documents)

# ✅ Setup the vectorstore once at start
chunks = load_script_chunks()
embedding = OpenAIEmbeddings()
vectorstore = ChromaDB.from_documents(chunks, embedding)

# ✅ Session memory for script progress
session_memory = {}

class MemoryEngine:
    def __init__(self):
        self.vectorstore = vectorstore
        self.session_memory = {}

    def reset_script(self, call_sid):
        self.session_memory[call_sid] = {"step": 0}

    def generate_response(self, call_sid, user_input):
        memory = self.session_memory.get(call_sid, {"step": 0})
        step = memory["step"]

        if step < len(chunks):
            response = chunks[step].page_content
            self.session_memory[call_sid]["step"] += 1
            return {"response": response, "sources": ["script"]}
        else:
            # After script is done, switch to fallback vector QA
            retriever = self.vectorstore.as_retriever(search_kwargs={"k": 2})
            qa = RetrievalQA.from_chain_type(
                llm=ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7, request_timeout=8, max_tokens=256),
                retriever=retriever
            )
            answer = qa.run(user_input)
            return {"response": answer, "sources": ["vector"]}
