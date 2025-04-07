from langchain.chains import RetrievalQA
from langchain_community.chat_models import ChatOpenAI
from memory_engine import vectorstore

retriever = vectorstore.as_retriever(search_kwargs={"k": 2})

qa = RetrievalQA.from_chain_type(
    llm=ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0.7,
        request_timeout=8,
        max_tokens=256
    ),
    retriever=retriever
)

query = "What should I say if the customer says it's too expensive?"
response = qa.run(query)

print("💬 Rachel says:", response)
