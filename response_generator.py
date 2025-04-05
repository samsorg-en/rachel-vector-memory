from langchain.chains import RetrievalQA
from langchain_community.chat_models import ChatOpenAI
from memory_engine import vectorstore

# 🔎 Limit how many chunks Rachel retrieves (keeps it fast + under token limits)
retriever = vectorstore.as_retriever(search_kwargs={"k": 2})

# 🧠 Use ChatOpenAI with tuned settings for faster, clearer replies
qa = RetrievalQA.from_chain_type(
    llm=ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0.7,  # More natural tone
        request_timeout=8,  # Respond faster
        max_tokens=256  # Shorter, cleaner answers
    ),
    retriever=retriever)

# ❓ Replace this objection with anything you want to test
query = "What should I say if the customer says it's too expensive?"

# 🚀 Get Rachel's response using trained call memory
response = qa.run(query)

# 🗣️ Print the answer
print("💬 Rachel says:", response)
