from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import os
from dotenv import load_dotenv
from pinecone.grpc import PineconeGRPC as Pinecone
import sys
import time
from typing import List

# Load the environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# CORS setup
origins = [
    os.getenv("FRONTEND_URL")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

my_api_key = os.getenv("PINECONE_API_KEY")
my_environment = os.getenv("PINECONE_ENVIRONMENT")

# Check if the API key and environment are loaded successfully
if my_api_key is None:
    print("Error: Pinecone API key not found. Please include it in the .env file.")
    sys.exit(1)

if my_environment is None:
    print("Error: Pinecone environment not found. Please include it in the .env file.")
    sys.exit(1)

# Initialize Pinecone and SentenceTransformer Model
pc = Pinecone(api_key=my_api_key)
index_name = "sarcathon-faq"
model = SentenceTransformer('all-MiniLM-L6-v2')

#Making sure Index exists in Pinecone Database
available_indexes = pc.list_indexes()
if index_name not in [idx["name"] for idx in available_indexes]:
    raise HTTPException(status_code=500, detail="Index does not exist.")

# Wait for the index to be ready
while not pc.describe_index(index_name).status['ready']:
    time.sleep(1)

#connecting to the index
index = pc.Index(index_name)
total_vector_count = index.describe_index_stats()['total_vector_count']
anns_threshold = 10**3

# Define the data models
class QueryRequest(BaseModel):
    query: str

# Home route of backend server
@app.get("/")
def home():
    return {"message": "Welcome to the FAQ API"}

# search route
@app.post("/search")
def search_faq(request: QueryRequest):
    user_query = request.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # Convert the user's query into an embedding
    query_embedding = model.encode(user_query).tolist()

    # Query Pinecone for similar FAQs
    if total_vector_count <= anns_threshold:
        response = index.query(
            namespace="sarc-namespace",
            vector=query_embedding,
            top_k=5,
            include_values=False,
            include_metadata=True,
            ef=total_vector_count
        )
    else:
        response = index.query(
            namespace="sarc-namespace",
            vector=query_embedding,
            top_k=5,
            include_values=False,
            include_metadata=True
        )

    if not response['matches']:
        raise HTTPException(status_code=404, detail="No relevant FAQs found.")

    # Extract FAQs
    english_results = [
        {
            "id": match["id"],
            "score": match["score"],
            "question": match["metadata"]["question"],
            "answer": match["metadata"]["answer"],
            "category": match["metadata"]["category"]
        }
        for match in response['matches']
    ]

    return english_results