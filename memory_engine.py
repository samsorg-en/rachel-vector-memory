import os
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.chains.question_answering import load_qa_chain


class MemoryEngine:

    def __init__(self, transcript_dir="calls", db_path="./chroma_db"):
        self.transcript_dir = transcript_dir
        self.db_path = db_path
        self.embedding = OpenAIEmbeddings()
        self.vectorstore = Chroma(
            persist_directory=self.db_path,
            embedding_function=self.embedding
        )
        self.llm = ChatOpenAI(model="gpt-4", temperature=0.4)
        self.qa_chain = load_qa_chain(self.llm, chain_type="stuff")

    def process_transcripts(self):
        total = 0
        for file in os.listdir(self.transcript_dir):
            if file.endswith(".txt"):
                loader = TextLoader(os.path.join(self.transcript_dir, file))
                docs = loader.load()
                self.vectorstore.add_documents(docs)
                total += 1
        return total

    def generate_response(self, objection_text):
        # ✅ LIMIT k=4 to avoid token overflow in GPT-4
        related_docs = self.vectorstore.similarity_search(objection_text, k=2)
        result = self.qa_chain.run(input_documents=related_docs, question=objection_text)

        logger.info(f"👂 Lane's Debug, #4 in Memory Engine: {result}")
        return {
            "response": result,
            "sources": [doc.metadata.get("source", "unknown") for doc in related_docs]
        }

    def get_stats(self):
        return {
            "total_segments": len(self.vectorstore.get()["ids"]),
            "total_sources": len(os.listdir(self.transcript_dir)),
            "vector_dimension": self.embedding.client.model_dimensions["text-embedding-ada-002"]
        }
