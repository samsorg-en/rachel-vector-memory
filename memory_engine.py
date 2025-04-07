import os
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate

class MemoryEngine:
    def __init__(self, transcript_dir="calls", db_path="./chroma_db"):
        self.transcript_dir = transcript_dir
        self.script_path = os.path.join(transcript_dir, "script")
        self.db_path = db_path
        self.embedding = OpenAIEmbeddings()
        self.vectorstore = Chroma(
            persist_directory=self.db_path,
            embedding_function=self.embedding
        )
        self.llm = ChatOpenAI(model="gpt-4", temperature=0.4)
        prompt_template = PromptTemplate.from_template(
            "Answer the question based on memory: {context}\n\nQ: {question}\nA:"
        )
        self.qa_chain = LLMChain(llm=self.llm, prompt=prompt_template)
        self.script_lines = []
        self.script_index = 0
        self._load_script()

    def _load_script(self):
        """Load all .txt lines from script directory with [gather] markers."""
        self.script_lines = []
        if not os.path.exists(self.script_path):
            print(f"❌ Script folder not found: {self.script_path}")
            return

        for filename in sorted(os.listdir(self.script_path)):
            if filename.endswith(".txt") and not filename.startswith("."):
                with open(os.path.join(self.script_path, filename), "r") as f:
                    content = f.read().strip()
                    segments = [line.strip() for line in content.split("[gather]") if line.strip()]
                    self.script_lines.extend(segments)

        self.script_index = 0
        print(f"✅ Loaded {len(self.script_lines)} script blocks.")

    def process_transcripts(self):
        """Load memory vector DB from transcript .txts (excluding script files)"""
        total = 0
        for file in os.listdir(self.transcript_dir):
            if file.endswith(".txt") and "script" not in file and not file.startswith("."):
                loader = TextLoader(os.path.join(self.transcript_dir, file))
                docs = loader.load()
                self.vectorstore.add_documents(docs)
                total += 1
        return total

    def generate_response(self, user_input):
        """Return next script line or fallback to memory"""
        if self.script_index < len(self.script_lines):
            response = self.script_lines[self.script_index]
            self.script_index += 1
            return {
                "response": response,
                "sources": ["script"]
            }

        try:
            related_docs = self.vectorstore.similarity_search(user_input, k=2)
            context = "\n".join([doc.page_content for doc in related_docs])
            result = self.qa_chain.run({"context": context, "question": user_input})
            return {
                "response": result,
                "sources": [doc.metadata.get("source", "unknown") for doc in related_docs]
            }
        except Exception as e:
            return {
                "response": f"I'm sorry, I'm having trouble accessing memory. Here's the error: {str(e)}",
                "sources": []
            }

    def reset_script(self):
        """Reset script for next call"""
        self.script_index = 0

    def get_stats(self):
        return {
            "total_segments": len(self.vectorstore.get()["ids"]),
            "total_sources": len([
                f for f in os.listdir(self.transcript_dir)
                if f.endswith(".txt") and not f.startswith(".") and "script" not in f
            ]),
            "vector_dimension": self.embedding.client.model_dimensions["text-embedding-ada-002"]
        }
