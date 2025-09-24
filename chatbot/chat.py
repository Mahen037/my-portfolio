import os
from dotenv import load_dotenv
load_dotenv("./.env")
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader, PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.prompts import PromptTemplate
from langchain_huggingface import HuggingFaceEndpoint
from huggingface_hub import InferenceClient
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
import time
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

class Chatbot:
    def __init__(self):
        print("🔄 Loading context documents...")
        start_time = time.time()
        
        # Load all text and PDF files from the context directory
        text_loader = DirectoryLoader(
            'chatbot/context',
            glob="**/*.txt",
            loader_cls=TextLoader
        )
        
        # Load documents from the loader
        documents = text_loader.load()
        
        print(f"📚 Loaded {len(documents)} documents")
        
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=30)
        docs = text_splitter.split_documents(documents)
        
        print("🔍 Creating embeddings...")
        # embeddings
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/multi-qa-distilbert-cos-v1",
            model_kwargs={
                'device': 'cpu',
                'token': os.getenv('HUGGINGFACE_API_KEY')
            }
        )

        docsearch = FAISS.from_documents(docs, embeddings)
        # Store docsearch as instance variable
        self.docsearch = docsearch
        
        print("🤖 Initializing AI model...")
        # Define the repo ID and connect to Mixtral model on Huggingface
        repo_id = "mistralai/Mixtral-8x7B-Instruct-v0.1"
        # low-level HF client for chat_completion
        self.llm = InferenceClient(
            "mistralai/Mixtral-8x7B-Instruct-v0.1",
            token=os.getenv("HUGGINGFACE_API_KEY")
        )

        # Store embeddings model for similarity checking
        self.embeddings_model = embeddings
        
        # Store conversation history
        self.conversation_history = []

        # Create embeddings for problematic meta-commentary phrases
        self.problematic_phrases = [
            "based on the documents I have",
            "according to the context provided to me", 
            "from the information I've been given",
            "the documents show that",
            "based on my knowledge base",
            "from the context I can see",
            "according to the sources I have"
        ]

        # Create embeddings for these phrases
        self.problematic_embeddings = [
            self.embeddings_model.embed_query(phrase) 
            for phrase in self.problematic_phrases
        ]
        
        # prompt template
        template = """You are Mahendra Kumar, an expert consultant. Answer questions directly and professionally.

CRITICAL: Never say "based on documents", "according to context", or mention your information/meta-commentary sources.

RULES:
- NEVER mention "documents", "context", "sources", or "based on".
- NEVER mention your information/meta-commentary sources.
- State facts directly without explaining how you know them.
- For greetings, reply with a brief, polite acknowledgment ONLY.
- If you don't know, respond with: "I'm sorry, I don't have that information."

Conversation:
{conversation_history}

Information/Context:
{context}

Question: {question}

Answer directly:"""

        # Refinement prompt for when we detect meta-commentary
        refinement_template = """Your previous response mentioned your information sources, which isn't needed. Please rewrite your answer to be more direct and professional.

Original question: {question}

Your previous response: {previous_response}

Please provide a refined answer that:
- Answers the question directly
- Doesn't mention documents, context, or sources
- States facts as an expert would
"""

        prompt = PromptTemplate(
            template=template, 
            input_variables=["context", "question", "conversation_history"]
        )

        self.refinement_prompt = PromptTemplate(
            template=refinement_template,
            input_variables=["question", "previous_response"]
        )

        def llm_wrapper(prompt_text):
            if hasattr(prompt_text, "to_string"):
                prompt_text = prompt_text.to_string()
            
            try:
                response = self.llm.chat_completion(
                    model="mistralai/Mixtral-8x7B-Instruct-v0.1",
                    messages=[{"role": "user", "content": prompt_text}],
                    max_tokens=100,  # Less tokens for more focused responses
                    temperature=0.4,  # Slightly higher for natural responses
                    top_p=0.95
                )
                answer = response.choices[0].message["content"]
                return answer.strip()
            except Exception as e:
                print(f"❌ AI API Error: {e}")
                return "I'm having trouble connecting to my AI service right now. Please try again in a moment."

        self.prompt = prompt
        self.llm_wrapper = llm_wrapper
        
        init_time = time.time() - start_time
        print(f"✅ Chatbot initialized in {init_time:.2f} seconds!")


    def check_meta_commentary_similarity(self, response, threshold=0.7):
        """
        Check if response contains meta-commentary using cosine similarity
        Returns True if problematic content is detected
        """
        try:
            # Get embedding for the response
            response_embedding = self.embeddings_model.embed_query(response)
            
            # Calculate similarity with each problematic phrase
            similarities = []
            for prob_embedding in self.problematic_embeddings:
                similarity = cosine_similarity(
                    [response_embedding], 
                    [prob_embedding]
                )[0][0]
                similarities.append(similarity)
            
            # Check if any similarity exceeds threshold
            max_similarity = max(similarities)
            return max_similarity > threshold, max_similarity
            
        except Exception as e:
            print(f"Error in similarity check: {e}")
            return False, 0.0

    def refine_response(self, original_question, problematic_response):
        """Ask the model to refine its response"""
        try:
            refinement_prompt_text = self.refinement_prompt.format(
                question=original_question,
                previous_response=problematic_response
            )
            
            refined_response = self.llm_wrapper(refinement_prompt_text)
            return refined_response
            
        except Exception as e:
            print(f"Error in refinement: {e}")
            return "I'm sorry, I don't have that information."

    def get_response(self, user_message):
        """Get response with conversation context"""
        try:
            # Add user message to history
            self.conversation_history.append(f"User: {user_message}")
            
            # Keep only last 10 messages to avoid context overflow
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            
            # Format conversation history
            conv_history = "\n".join(self.conversation_history[-6:])  # Last 6 messages
            
            # Create the prompt with context
            prompt_text = self.prompt.format(
                context=self.docsearch.as_retriever().get_relevant_documents(user_message),
                question=user_message,
                conversation_history=conv_history
            )
            
            # Get response
            response = self.llm_wrapper(prompt_text)

            # Check for meta-commentary using cosine similarity
            is_problematic, similarity_score = self.check_meta_commentary_similarity(response)

            if is_problematic:
                print(f"🔄 Detected meta-commentary (similarity: {similarity_score:.3f}). Refining response...")
                response = self.refine_response(user_message, response)
                
                # Double-check the refined response
                is_still_problematic, new_similarity = self.check_meta_commentary_similarity(response)
                if is_still_problematic:
                    print(f"⚠️ Refined response still problematic. Using fallback.")
                    response = "I'm sorry, I don't have that information."
            
            
            # Add bot response to history
            self.conversation_history.append(f"Assistant: {response}")
            
            return response
            
        except Exception as e:
            print(f"❌ Error in get_response: {e}")
            return "I'm sorry, I encountered an error. Please try again."


if __name__ == "__main__":
    bot = Chatbot()
    while True:
        user_input = input("Ask me anything: ")
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("Goodbye!")
            break
        result = bot.get_response(user_input)
        print(result)