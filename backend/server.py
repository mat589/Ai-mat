from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime
import asyncio
import json
import base64
from io import BytesIO

# Import emergentintegrations
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from emergentintegrations.llm.gemeni.image_generation import GeminiImageGeneration

# Import Hugging Face Diffusers for fallback image generation
from diffusers import StableDiffusionPipeline
import torch

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Gemini API Keys Pool
GEMINI_KEYS = [
    os.environ['GEMINI_API_KEY_1'],
    os.environ['GEMINI_API_KEY_2'],
    os.environ['GEMINI_API_KEY_3'],
    os.environ['GEMINI_API_KEY_4'],
    os.environ['GEMINI_API_KEY_5'],
    os.environ['GEMINI_API_KEY_6'],
    os.environ['GEMINI_API_KEY_7'],
    os.environ['GEMINI_API_KEY_8'],
    os.environ['GEMINI_API_KEY_9'],
    os.environ['GEMINI_API_KEY_10'],
]

# Create the main app without a prefix
app = FastAPI(title="AI Chatbot API", description="All-in-one AI chatbot with chat, image generation, and analysis")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Global key rotation state
current_key_index = 0
key_usage_count = {}

# Initialize usage tracking
for i, key in enumerate(GEMINI_KEYS):
    key_usage_count[i] = 0

# Hugging Face Stable Diffusion Pipeline (lazy loaded)
_hf_pipeline = None

def get_hf_pipeline():
    """Get or create Hugging Face Stable Diffusion pipeline"""
    global _hf_pipeline
    if _hf_pipeline is None:
        try:
            model_id = "CompVis/stable-diffusion-v1-4"
            device = "cuda" if torch.cuda.is_available() else "cpu"
            _hf_pipeline = StableDiffusionPipeline.from_pretrained(
                model_id,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                safety_checker=None,
                requires_safety_checker=False
            )
            _hf_pipeline.to(device)
            logger.info(f"Loaded Stable Diffusion pipeline on device: {device}")
        except Exception as e:
            logger.error(f"Failed to load Stable Diffusion pipeline: {str(e)}")
            _hf_pipeline = None
    return _hf_pipeline

# Key Management Functions
def get_next_api_key():
    """Smart key rotation with usage tracking"""
    global current_key_index
    
    # Find key with lowest usage
    min_usage = min(key_usage_count.values())
    for i, usage in key_usage_count.items():
        if usage == min_usage:
            current_key_index = i
            break
    
    key_usage_count[current_key_index] += 1
    return GEMINI_KEYS[current_key_index]

async def create_gemini_chat(session_id: str, system_message: str = "You are a helpful AI assistant."):
    """Create a new Gemini chat instance with key rotation"""
    api_key = get_next_api_key()
    chat = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message=system_message
    ).with_model("gemini", "gemini-2.0-flash")
    return chat

async def create_gemini_image_generator():
    """Create Gemini image generator with key rotation"""
    api_key = get_next_api_key()
    return GeminiImageGeneration(api_key=api_key)

# Data Models
class ChatSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: str  # "user" or "assistant"
    content: str
    image_base64: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    image_base64: Optional[str] = None

class ImageGenerationRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None

class ChatSessionCreate(BaseModel):
    title: str

# Chat Endpoints
@api_router.post("/chat/sessions", response_model=ChatSession)
async def create_chat_session(session: ChatSessionCreate):
    """Create a new chat session"""
    session_obj = ChatSession(title=session.title)
    session_dict = session_obj.dict()
    await db.chat_sessions.insert_one(session_dict)
    return session_obj

@api_router.get("/chat/sessions", response_model=List[ChatSession])
async def get_chat_sessions():
    """Get all chat sessions"""
    sessions = await db.chat_sessions.find().sort("updated_at", -1).to_list(100)
    return [ChatSession(**session) for session in sessions]

@api_router.get("/chat/sessions/{session_id}/messages", response_model=List[ChatMessage])
async def get_chat_messages(session_id: str):
    """Get messages for a specific chat session"""
    messages = await db.chat_messages.find({"session_id": session_id}).sort("timestamp", 1).to_list(1000)
    return [ChatMessage(**message) for message in messages]

@api_router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete a chat session and all its messages"""
    await db.chat_sessions.delete_one({"id": session_id})
    await db.chat_messages.delete_many({"session_id": session_id})
    return {"message": "Session deleted successfully"}

async def save_message(session_id: str, role: str, content: str, image_base64: Optional[str] = None):
    """Save message to database"""
    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        image_base64=image_base64
    )
    await db.chat_messages.insert_one(message.dict())
    
    # Update session timestamp
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": {"updated_at": datetime.utcnow()}}
    )
    return message

@api_router.post("/chat/message")
async def chat_message(request: ChatRequest):
    """Send a chat message and get AI response"""
    try:
        session_id = request.session_id or str(uuid.uuid4())
        
        # Save user message
        user_message = await save_message(session_id, "user", request.message, request.image_base64)
        
        # Create chat instance
        chat = await create_gemini_chat(session_id)
        
        # Prepare user message for AI
        user_msg_content = []
        if request.image_base64:
            # Add image content
            image_content = ImageContent(image_base64=request.image_base64)
            user_msg = UserMessage(
                text=request.message,
                file_contents=[image_content]
            )
        else:
            user_msg = UserMessage(text=request.message)
        
        # Get AI response
        ai_response = await chat.send_message(user_msg)
        
        # Save AI response
        ai_message = await save_message(session_id, "assistant", ai_response)
        
        return {
            "session_id": session_id,
            "user_message": user_message.dict(),
            "ai_response": ai_message.dict(),
            "key_usage_stats": key_usage_count
        }
        
    except Exception as e:
        logging.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

@api_router.post("/chat/stream/{session_id}")
async def stream_chat(session_id: str, request: ChatRequest):
    """Stream chat response in real-time"""
    async def generate_response():
        try:
            # Save user message
            await save_message(session_id, "user", request.message, request.image_base64)
            
            # Create chat instance
            chat = await create_gemini_chat(session_id)
            
            # Prepare user message
            if request.image_base64:
                image_content = ImageContent(image_base64=request.image_base64)
                user_msg = UserMessage(
                    text=request.message,
                    file_contents=[image_content]
                )
            else:
                user_msg = UserMessage(text=request.message)
            
            # Stream response (Note: emergentintegrations may not support streaming yet)
            # This is a placeholder for streaming implementation
            ai_response = await chat.send_message(user_msg)
            
            # Simulate streaming by yielding chunks
            words = ai_response.split()
            full_response = ""
            
            for word in words:
                full_response += word + " "
                yield f"data: {json.dumps({'content': word + ' ', 'done': False})}\n\n"
                await asyncio.sleep(0.05)  # Small delay for streaming effect
            
            # Save complete response
            await save_message(session_id, "assistant", ai_response)
            
            yield f"data: {json.dumps({'content': '', 'done': True, 'session_id': session_id})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
    
    return StreamingResponse(
        generate_response(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

async def generate_image_huggingface(prompt: str):
    """Generate image using Hugging Face Stable Diffusion as fallback"""
    try:
        pipeline = get_hf_pipeline()
        if pipeline is None:
            raise Exception("Stable Diffusion pipeline not available")
        
        # Generate image
        with torch.inference_mode():
            image = pipeline(prompt, num_inference_steps=20, guidance_scale=7.5).images[0]
        
        # Convert to base64
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return image_base64
    except Exception as e:
        logger.error(f"Hugging Face image generation error: {str(e)}")
        raise e

# Image Generation Endpoints
@api_router.post("/image/generate")
async def generate_image(request: ImageGenerationRequest):
    """Generate image from text prompt with Gemini and Hugging Face fallback"""
    try:
        session_id = request.session_id or str(uuid.uuid4())
        
        # Save user request
        await save_message(session_id, "user", f"Generate image: {request.prompt}")
        
        image_base64 = None
        generation_method = "unknown"
        
        # Try Gemini first
        try:
            # Create image generator
            image_gen = await create_gemini_image_generator()
            
            # Generate image
            images = await image_gen.generate_images(
                prompt=request.prompt,
                model="imagen-3.0-generate-002",
                number_of_images=1
            )
            
            if images and len(images) > 0:
                # Convert to base64
                image_base64 = base64.b64encode(images[0]).decode('utf-8')
                generation_method = "Gemini Imagen"
                logger.info("Image generated successfully using Gemini")
            
        except Exception as gemini_error:
            logger.warning(f"Gemini image generation failed: {str(gemini_error)}")
            
            # Fallback to Hugging Face Stable Diffusion
            try:
                image_base64 = await generate_image_huggingface(request.prompt)
                generation_method = "Hugging Face Stable Diffusion"
                logger.info("Image generated successfully using Hugging Face fallback")
            except Exception as hf_error:
                logger.error(f"Hugging Face fallback also failed: {str(hf_error)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Both image generation methods failed. Gemini: {str(gemini_error)}, HuggingFace: {str(hf_error)}"
                )
        
        if image_base64:
            # Save AI response with image
            ai_message = await save_message(
                session_id, 
                "assistant", 
                f"Generated image using {generation_method}: {request.prompt}",
                image_base64
            )
            
            return {
                "session_id": session_id,
                "image_base64": image_base64,
                "prompt": request.prompt,
                "generation_method": generation_method,
                "message": ai_message.dict(),
                "key_usage_stats": key_usage_count
            }
        else:
            raise HTTPException(status_code=500, detail="No image was generated by any method")
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Image generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")

@api_router.post("/image/analyze")
async def analyze_image(file: UploadFile = File(...), prompt: str = "Describe this image in detail"):
    """Analyze an uploaded image"""
    try:
        # Read image file
        image_data = await file.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        session_id = str(uuid.uuid4())
        
        # Save user request
        await save_message(session_id, "user", f"Analyze image: {prompt}", image_base64)
        
        # Create chat instance
        chat = await create_gemini_chat(session_id)
        
        # Analyze image
        image_content = ImageContent(image_base64=image_base64)
        user_msg = UserMessage(
            text=prompt,
            file_contents=[image_content]
        )
        
        ai_response = await chat.send_message(user_msg)
        
        # Save AI response
        ai_message = await save_message(session_id, "assistant", ai_response)
        
        return {
            "session_id": session_id,
            "analysis": ai_response,
            "prompt": prompt,
            "message": ai_message.dict(),
            "key_usage_stats": key_usage_count
        }
        
    except Exception as e:
        logging.error(f"Image analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Image analysis failed: {str(e)}")

# System Status Endpoints
@api_router.get("/status")
async def get_system_status():
    """Get system status including key usage"""
    return {
        "status": "online",
        "total_keys": len(GEMINI_KEYS),
        "key_usage_stats": key_usage_count,
        "current_key_index": current_key_index,
        "total_requests": sum(key_usage_count.values()),
        "database_connected": True
    }

@api_router.get("/")
async def root():
    return {"message": "AI Chatbot API is running!", "version": "1.0.0"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()