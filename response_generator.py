from memory_engine import MemoryEngine

# ✅ Load the shared memory engine
engine = MemoryEngine()

# ✅ Example objection
query = "What should I say if the customer says it's too expensive?"

# ✅ Run it through the QA fallback
response = engine.qa.run(query)

print("💬 Rachel says:", response)
