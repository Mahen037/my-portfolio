from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import mimetypes
from pathlib import Path
from pydantic import BaseModel, EmailStr
import smtplib
import logging
from email.mime.text import MIMEText
from dotenv import load_dotenv
import sys
from chatbot.chat import Chatbot


# Add chatbot directory to path
sys.path.append(str(Path(__file__).parent / "chatbot"))


env_path = Path(__file__).parent / "chatbot/.env"
load_dotenv(env_path)


# Create FastAPI app
app = FastAPI(
    title="Mahendra Kumar Portfolio",
    description="Portfolio website for Mahendra Kumar",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Get the directory where this script is located
current_dir = Path(__file__).parent

# Mount static files for CSS, JS, and other assets
app.mount("/static", StaticFiles(directory="static"), name="static")


# Initialize chatbot instance
chatbot_instance = None

@app.on_event("startup")
async def startup_event():
    global chatbot_instance
    """Get or create chatbot instance"""
    if chatbot_instance is None:
        try:
            chatbot_instance = Chatbot()
        except Exception as e:
            print(f"Error initializing chatbot: {e}")

def get_chatbot():
    if chatbot_instance is None:
        raise HTTPException(status_code=500, detail="Chatbot not available")
    return chatbot_instance



@app.get("/", response_class=HTMLResponse)
async def read_index():
    """Serve the main portfolio page"""
    index_path = current_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Portfolio page not found")
    return FileResponse(index_path)


@app.get("/video")
async def get_video():
    """Serve background video"""
    video_path = current_dir / "Mahendra_BGVideo.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    
    def iterfile():
        with open(video_path, mode="rb") as file_like:
            yield from file_like
    
    return StreamingResponse(
        iterfile(), 
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"}
    )

class ContactForm(BaseModel):
    firstName: str
    lastName: str
    email: EmailStr
    subject: str
    message: str

class EmailResponse(BaseModel):
    success: bool
    message: str

class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    success: bool

def send_email(contact_data: ContactForm):
    try:
        msg = MIMEText(f"""{contact_data.message}
        
Best regards,
{contact_data.firstName} {contact_data.lastName}
{contact_data.email}
""")
        msg['Subject'] = f"Portfolio Contact: {contact_data.subject}"
        msg['From'] = contact_data.email
        msg['To'] = os.getenv("EMAIL_USERNAME")
        server = smtplib.SMTP(os.getenv("SMTP_SERVER"), int(os.getenv("SMTP_PORT")))
        server.starttls()
        server.login(os.getenv("EMAIL_USERNAME"), os.getenv("EMAIL_PASSWORD"))
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(e)
        return False


@app.post("/contact", response_model=EmailResponse)
async def send_contact_email(contact_data: ContactForm):
    """Handle contact form submission and send email"""
    try:
        # Send email
        success = send_email(contact_data)
        
        if success:
            return EmailResponse(
                success=True,
                message="Thank you for your message! I'll get back to you soon."
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to send email. Please try again later.")
            
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Contact form error: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while processing your request.")


@app.post("/chat", response_model=ChatResponse)
async def chat_with_bot(chat_data: ChatMessage):
    """Handle chatbot messages"""
    try:
        chatbot = get_chatbot()
        if chatbot is None:
            raise HTTPException(status_code=500, detail="Chatbot is not available. Please try again later.")
        
        response = chatbot.get_response(chat_data.message)
        print('Chatbot response:', response);
        return ChatResponse(
            response=response,
            success=True
        )
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while processing your message.")


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return HTMLResponse(
        content="<h1>404 - Page Not Found</h1><p>The requested page could not be found.</p>",
        status_code=404
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    return HTMLResponse(
        content="<h1>500 - Internal Server Error</h1><p>Something went wrong on our end.</p>",
        status_code=500
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=True,  # Enable auto-reload for development
        log_level="info"
    )