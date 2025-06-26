import React, { useState, useEffect, useRef } from "react";
import "./App.css";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Chat Message Component
const ChatMessage = ({ message, isUser }) => {
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
          isUser
            ? 'bg-blue-500 text-white'
            : 'bg-gray-200 text-gray-800'
        }`}
      >
        {message.image_base64 && (
          <img
            src={`data:image/jpeg;base64,${message.image_base64}`}
            alt="Uploaded"
            className="w-full h-auto rounded-lg mb-2"
          />
        )}
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        <p className="text-xs opacity-70 mt-1">
          {new Date(message.timestamp).toLocaleTimeString()}
        </p>
      </div>
    </div>
  );
};

// Session Sidebar Component
const SessionSidebar = ({ sessions, currentSession, onSessionSelect, onNewSession, onDeleteSession }) => {
  return (
    <div className="w-64 bg-gray-100 h-full p-4 overflow-y-auto">
      <button
        onClick={onNewSession}
        className="w-full bg-blue-500 text-white py-2 px-4 rounded-lg hover:bg-blue-600 mb-4"
      >
        + New Chat
      </button>
      
      <div className="space-y-2">
        {sessions.map((session) => (
          <div
            key={session.id}
            className={`p-3 rounded-lg cursor-pointer hover:bg-gray-200 ${
              currentSession?.id === session.id ? 'bg-blue-100 border-l-4 border-blue-500' : ''
            }`}
            onClick={() => onSessionSelect(session)}
          >
            <h3 className="font-medium text-sm truncate">{session.title}</h3>
            <p className="text-xs text-gray-500">
              {new Date(session.updated_at).toLocaleDateString()}
            </p>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDeleteSession(session.id);
              }}
              className="text-red-500 text-xs hover:text-red-700 mt-1"
            >
              Delete
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

// Image Generation Component
const ImageGenerator = ({ onGenerate, isGenerating }) => {
  const [prompt, setPrompt] = useState("");

  const handleGenerate = () => {
    if (prompt.trim()) {
      onGenerate(prompt);
      setPrompt("");
    }
  };

  return (
    <div className="bg-purple-50 p-4 rounded-lg mb-4">
      <h3 className="font-medium text-purple-800 mb-2">🎨 Generate Image</h3>
      <div className="flex space-x-2">
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe the image you want to generate..."
          className="flex-1 px-3 py-2 border border-purple-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
          onKeyPress={(e) => e.key === 'Enter' && handleGenerate()}
          disabled={isGenerating}
        />
        <button
          onClick={handleGenerate}
          disabled={isGenerating || !prompt.trim()}
          className="bg-purple-500 text-white px-4 py-2 rounded-lg hover:bg-purple-600 disabled:bg-gray-400"
        >
          {isGenerating ? "Generating..." : "Generate"}
        </button>
      </div>
    </div>
  );
};

// Image Upload Component
const ImageUpload = ({ onUpload, isAnalyzing }) => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [prompt, setPrompt] = useState("Describe this image in detail");
  const fileInputRef = useRef(null);

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleUpload = () => {
    if (selectedFile) {
      onUpload(selectedFile, prompt);
      setSelectedFile(null);
      setPrompt("Describe this image in detail");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  return (
    <div className="bg-green-50 p-4 rounded-lg mb-4">
      <h3 className="font-medium text-green-800 mb-2">📷 Analyze Image</h3>
      <div className="space-y-2">
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleFileSelect}
          className="w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-green-500 file:text-white hover:file:bg-green-600"
          disabled={isAnalyzing}
        />
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="What would you like to know about this image?"
          className="w-full px-3 py-2 border border-green-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500"
          disabled={isAnalyzing}
        />
        <button
          onClick={handleUpload}
          disabled={isAnalyzing || !selectedFile}
          className="w-full bg-green-500 text-white px-4 py-2 rounded-lg hover:bg-green-600 disabled:bg-gray-400"
        >
          {isAnalyzing ? "Analyzing..." : "Analyze Image"}
        </button>
      </div>
    </div>
  );
};

// Main App Component
function App() {
  const [sessions, setSessions] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [systemStatus, setSystemStatus] = useState(null);
  const messagesEndRef = useRef(null);

  // Scroll to bottom of messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load sessions on mount
  useEffect(() => {
    loadSessions();
    loadSystemStatus();
  }, []);

  const loadSessions = async () => {
    try {
      const response = await axios.get(`${API}/chat/sessions`);
      setSessions(response.data);
    } catch (error) {
      console.error("Failed to load sessions:", error);
    }
  };

  const loadSystemStatus = async () => {
    try {
      const response = await axios.get(`${API}/status`);
      setSystemStatus(response.data);
    } catch (error) {
      console.error("Failed to load system status:", error);
    }
  };

  const loadMessages = async (sessionId) => {
    try {
      const response = await axios.get(`${API}/chat/sessions/${sessionId}/messages`);
      setMessages(response.data);
    } catch (error) {
      console.error("Failed to load messages:", error);
      setMessages([]);
    }
  };

  const createNewSession = async () => {
    try {
      const response = await axios.post(`${API}/chat/sessions`, {
        title: `Chat ${sessions.length + 1}`,
      });
      const newSession = response.data;
      setSessions([newSession, ...sessions]);
      setCurrentSession(newSession);
      setMessages([]);
    } catch (error) {
      console.error("Failed to create session:", error);
    }
  };

  const selectSession = (session) => {
    setCurrentSession(session);
    loadMessages(session.id);
  };

  const deleteSession = async (sessionId) => {
    try {
      await axios.delete(`${API}/chat/sessions/${sessionId}`);
      setSessions(sessions.filter(s => s.id !== sessionId));
      if (currentSession?.id === sessionId) {
        setCurrentSession(null);
        setMessages([]);
      }
    } catch (error) {
      console.error("Failed to delete session:", error);
    }
  };

  const sendMessage = async () => {
    if (!inputMessage.trim()) return;

    setIsLoading(true);
    const messageText = inputMessage;
    setInputMessage("");

    try {
      let sessionId = currentSession?.id;
      
      // Create new session if none exists
      if (!sessionId) {
        const sessionResponse = await axios.post(`${API}/chat/sessions`, {
          title: messageText.substring(0, 50) + "...",
        });
        sessionId = sessionResponse.data.id;
        setCurrentSession(sessionResponse.data);
        setSessions([sessionResponse.data, ...sessions]);
      }

      const response = await axios.post(`${API}/chat/message`, {
        message: messageText,
        session_id: sessionId,
      });

      // Reload messages to get the latest
      await loadMessages(sessionId);
      await loadSystemStatus();

    } catch (error) {
      console.error("Failed to send message:", error);
      // Re-add message to input on error
      setInputMessage(messageText);
    } finally {
      setIsLoading(false);
    }
  };

  const generateImage = async (prompt) => {
    setIsGenerating(true);
    try {
      let sessionId = currentSession?.id;
      
      // Create new session if none exists
      if (!sessionId) {
        const sessionResponse = await axios.post(`${API}/chat/sessions`, {
          title: `Image: ${prompt.substring(0, 30)}...`,
        });
        sessionId = sessionResponse.data.id;
        setCurrentSession(sessionResponse.data);
        setSessions([sessionResponse.data, ...sessions]);
      }

      const response = await axios.post(`${API}/image/generate`, {
        prompt,
        session_id: sessionId,
      });

      // Reload messages to see the generated image
      await loadMessages(sessionId);
      await loadSystemStatus();

    } catch (error) {
      console.error("Failed to generate image:", error);
      alert("Failed to generate image. Please try again.");
    } finally {
      setIsGenerating(false);
    }
  };

  const analyzeImage = async (file, prompt) => {
    setIsAnalyzing(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('prompt', prompt);

      const response = await axios.post(`${API}/image/analyze`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      // Create or update session
      let sessionId = response.data.session_id;
      const sessionResponse = await axios.post(`${API}/chat/sessions`, {
        title: `Image Analysis: ${prompt.substring(0, 30)}...`,
      });
      
      setCurrentSession(sessionResponse.data);
      setSessions([sessionResponse.data, ...sessions]);
      await loadMessages(sessionId);
      await loadSystemStatus();

    } catch (error) {
      console.error("Failed to analyze image:", error);
      alert("Failed to analyze image. Please try again.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <SessionSidebar
        sessions={sessions}
        currentSession={currentSession}
        onSessionSelect={selectSession}
        onNewSession={createNewSession}
        onDeleteSession={deleteSession}
      />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="bg-white border-b border-gray-200 p-4">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-xl font-bold text-gray-800">
                🤖 AI Chatbot - All-in-One
              </h1>
              <p className="text-sm text-gray-600">
                {currentSession ? currentSession.title : "Select or create a chat session"}
              </p>
            </div>
            {systemStatus && (
              <div className="text-sm text-gray-500">
                <span className="bg-green-100 text-green-800 px-2 py-1 rounded-full">
                  {systemStatus.total_requests} total requests
                </span>
                <span className="ml-2 bg-blue-100 text-blue-800 px-2 py-1 rounded-full">
                  {systemStatus.total_keys} API keys
                </span>
              </div>
            )}
          </div>
        </div>

        {/* AI Tools */}
        <div className="bg-white border-b border-gray-200 p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ImageGenerator onGenerate={generateImage} isGenerating={isGenerating} />
            <ImageUpload onUpload={analyzeImage} isAnalyzing={isAnalyzing} />
          </div>
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="text-center text-gray-500 mt-8">
              <div className="text-4xl mb-4">🤖</div>
              <h2 className="text-xl font-semibold mb-2">Welcome to AI Chatbot!</h2>
              <p className="text-gray-400">
                Start a conversation, generate images, or analyze photos. I'm here to help!
              </p>
              <div className="mt-4 text-sm text-gray-400">
                <p>✨ Real-time AI chat responses</p>
                <p>🎨 Generate images from text</p>
                <p>📷 Analyze and describe images</p>
                <p>🔄 Smart API key rotation for maximum usage</p>
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                isUser={message.role === "user"}
              />
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="bg-white border-t border-gray-200 p-4">
          <div className="flex space-x-2">
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder="Type your message here..."
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              onKeyPress={(e) => e.key === 'Enter' && !isLoading && sendMessage()}
              disabled={isLoading}
            />
            <button
              onClick={sendMessage}
              disabled={isLoading || !inputMessage.trim()}
              className="bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600 disabled:bg-gray-400"
            >
              {isLoading ? "Sending..." : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;