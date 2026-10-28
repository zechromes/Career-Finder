# Inspect the local Chroma server collection; this command prints stored documents.
import chromadb

# Connect to the server shown in your terminal
client = chromadb.HttpClient(host="localhost", port=8000)

# Access the default LangChain collection
collection = client.get_collection("langchain")

# Fetch and print the documents
results = collection.get()
print(f"Total documents found: {len(results['ids'])}")
print(results["documents"])
