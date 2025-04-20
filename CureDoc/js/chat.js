 // DOM Elements
 const chatBox = document.getElementById("chat-box");
 const welcomeMessage = document.getElementById("welcome-message");
 const queryInput = document.getElementById("query");
 const imageUpload = document.getElementById("image-upload");
 const imagePreviewContainer = document.getElementById("image-preview-container");
 const imagePreview = document.getElementById("image-preview");
 const promptContainer = document.getElementById("prompt-container");
 const loadingIndicator = document.getElementById("loading");
 const reportSection = document.getElementById("report-section");
 const downloadBtn = document.getElementById("download-report-btn");
 const chatHistoryContainer = document.getElementById("chat-history-container");

 // State variables
 let currentSessionId = null;
 let uploadedImageFile = null;
 let followupQuestions = [];
 let userResponses = [];
 let chatHistory = JSON.parse(localStorage.getItem("chatHistory")) || [];
 let cameraStream = null;

 // Initialize the app
 document.addEventListener('DOMContentLoaded', () => {
   updateChatHistory();
   
   // Load last chat if exists
   if (chatHistory.length > 0) {
     loadChatResponse(chatHistory.length - 1);
   }
 });

 // Toggle sidebar on mobile
 function toggleSidebar() {
   document.querySelector('.sidebar').classList.toggle('active');
 }

 // Remove welcome message when user starts interacting
 function removeWelcomeMessage() {
   if (welcomeMessage) {
     welcomeMessage.style.animation = "fadeOut 0.5s forwards";
     setTimeout(() => welcomeMessage.style.display = "none", 500);
   }
 }

 // Handle Enter key press
 function handleKeyDown(event) {
   if (event.key === 'Enter') {
     event.preventDefault();
     askQuery();
   }
 }

 // Main function to ask a medical question
 async function askQuery() {
   const query = queryInput.value.trim();
   if (!query) return;

   // Add user message to chat
   addMessageToChat('user', query, 'user-message');
   queryInput.value = '';
   
   // Show loading indicator
   showLoading(true);

   try {
     const response = await fetch("http://localhost:5009/ask", {
       method: "POST",
       headers: { "Content-Type": "application/json" },
       body: JSON.stringify({ query })
     });

     const data = await response.json();
     
     // Store in chat history
     const chatItem = { 
       type: 'text',
       query, 
       response: data.response,
       timestamp: new Date().toISOString()
     };
     chatHistory.push(chatItem);
     saveChatHistory();
     
     // Add bot response
     addMessageToChat('assistant', data.response, 'bot-message');

     // Handle follow-up questions if any
     if (data.followups && data.followups.length > 0) {
       setTimeout(() => {
         addMessageToChat('assistant', "To better understand your condition, please answer these follow-up questions:", 'bot-message');
         showFollowupQuestions(data.followups);
       }, 500);
     }
   } catch (error) {
     console.error("Error:", error);
     addMessageToChat('assistant', "Sorry, I encountered an error processing your request. Please try again.", 'bot-message');
   } finally {
     showLoading(false);
   }
 }

 // Add a message to the chat UI
 function addMessageToChat(sender, content, className) {
   const messageDiv = document.createElement("div");
   messageDiv.className = `message ${className}`;
   
   const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
   
   if (sender === 'user' && content.startsWith('Uploaded medical image')) {
     messageDiv.innerHTML = `
       <strong>You:</strong> 
       <div class="uploaded-image">
         <img src="${URL.createObjectURL(uploadedImageFile)}" alt="Uploaded medical image">
       </div>
       <span class="message-time">${time}</span>
     `;
   } else {
     messageDiv.innerHTML = `
       <strong>${sender === 'assistant' ? 'CureBot' : 'You'}:</strong> 
       ${content}
       <span class="message-time">${time}</span>
     `;
   }
   
   chatBox.appendChild(messageDiv);
   chatBox.scrollTop = chatBox.scrollHeight;
 }

 // Show loading indicator
 function showLoading(show) {
   loadingIndicator.style.display = show ? 'block' : 'none';
 }

 // Handle image upload
 function handleImageUpload(event) {
   const file = event.target.files[0];
   if (!file) return;

   uploadedImageFile = file;
   
   // Show preview
   const reader = new FileReader();
   reader.onload = function(e) {
     imagePreview.src = e.target.result;
     imagePreviewContainer.style.display = 'block';
     promptContainer.style.display = 'block';
     
     // Scroll to preview
     imagePreviewContainer.scrollIntoView({ behavior: 'smooth' });
   }
   reader.readAsDataURL(file);
 }

 // Cancel image upload
 function cancelImageUpload() {
   imageUpload.value = '';
   imagePreviewContainer.style.display = 'none';
   uploadedImageFile = null;
 }

 // Submit image for analysis
 async function submitImageForAnalysis() {
   const file = uploadedImageFile;
   const customPrompt = document.getElementById("custom-prompt").value.trim();
   
   if (!file) {
     alert('Please select an image first');
     return;
   }

   showLoading(true);
   
   const formData = new FormData();
   formData.append('image', file);
   if (customPrompt) {
     formData.append('prompt', customPrompt);
     formData.append('query', customPrompt);
   }

   try {
     const response = await fetch('http://localhost:5009/upload', {
       method: 'POST',
       body: formData
     });

     const data = await response.json();
     
     if (response.ok) {
       currentSessionId = data.session_id;
       
       // Add to chat history
       const chatItem = {
         type: 'image',
         query: customPrompt || 'Medical image analysis',
         response: data.result,
         imageUrl: URL.createObjectURL(file),
         timestamp: new Date().toISOString(),
         sessionId: data.session_id
       };
       chatHistory.push(chatItem);
       saveChatHistory();
       
       // Display in chat
       addMessageToChat('user', 'Uploaded medical image', 'user-message');
       if (customPrompt) {
         addMessageToChat('user', `Analysis request: ${customPrompt}`, 'user-message');
       }
       
       addMessageToChat('assistant', data.result, 'bot-message');
       
       // Show download button
       showDownloadButton(data.pdf_download);
       
       // Reset upload UI
       cancelImageUpload();
     } else {
       throw new Error(data.error || 'Failed to analyze image');
     }
   } catch (error) {
     console.error("Error:", error);
     addMessageToChat('assistant', `Error: ${error.message}`, 'bot-message');
   } finally {
     showLoading(false);
   }
 }

 // Show follow-up questions
 function showFollowupQuestions(questions) {
   followupQuestions = questions;
   
   const container = document.createElement('div');
   container.className = 'followup-container';
   container.innerHTML = `
     <h3>Follow-up Questions</h3>
     <ul class="followup-list" id="dynamic-followup-list"></ul>
     <div class="followup-button-container">
       <button class="followup-cancel" onclick="cancelFollowupQuestions()">Cancel</button>
       <button class="followup-submit" onclick="submitFollowupAnswers()">Submit Answers</button>
     </div>
   `;
   
   const list = container.querySelector('#dynamic-followup-list');
   questions.forEach((question, index) => {
     const li = document.createElement('li');
     li.innerHTML = `
       <div class="followup-question">${question}</div>
       <input type="text" class="followup-input" 
              placeholder="Your answer..." 
              data-index="${index}"
              onkeydown="handleFollowupKeydown(event, ${index})">
     `;
     list.appendChild(li);
   });
   
   chatBox.appendChild(container);
   chatBox.scrollTop = chatBox.scrollHeight;
   
   // Focus on first input
   const firstInput = container.querySelector('.followup-input');
   if (firstInput) firstInput.focus();
 }

 // Handle keyboard navigation in follow-ups
 function handleFollowupKeydown(event, index) {
   if (event.key === 'Enter') {
     event.preventDefault();
     const inputs = document.querySelectorAll(".followup-input");
     if (index < inputs.length - 1) {
       inputs[index + 1].focus();
     } else {
       submitFollowupAnswers();
     }
   }
 }

 // Cancel follow-up questions
 function cancelFollowupQuestions() {
   const container = document.querySelector('.followup-container');
   if (container) container.remove();
   followupQuestions = [];
 }

 // Submit follow-up answers
 async function submitFollowupAnswers() {
   const inputs = document.querySelectorAll(".followup-input");
   let allAnswered = true;
   
   // Validate all answers
   inputs.forEach(input => {
     if (!input.value.trim()) {
       input.classList.add("error");
       allAnswered = false;
     } else {
       input.classList.remove("error");
     }
   });

   if (!allAnswered) {
     addMessageToChat('assistant', "Please answer all follow-up questions before submitting.", 'bot-message');
     return;
   }

   // Collect answers
   const followups = [];
   const responses = [];
   
   inputs.forEach(input => {
     followups.push(followupQuestions[parseInt(input.dataset.index)]);
     responses.push(input.value.trim());
   });

   showLoading(true);
   
   try {
     const lastQuery = chatHistory[chatHistory.length - 1]?.query || '';
     
     const response = await fetch("http://localhost:5009/answer", {
       method: "POST",
       headers: { "Content-Type": "application/json" },
       body: JSON.stringify({
         query: lastQuery,
         followups,
         responses
       })
     });

     const data = await response.json();
     currentSessionId = data.session_id;
     
     // Remove follow-up UI
     const container = document.querySelector('.followup-container');
     if (container) container.remove();
     
     // Add final solution to chat
     addMessageToChat('assistant', data.final_solution, 'bot-message');
     
     // Update chat history
     if (chatHistory.length > 0) {
       chatHistory[chatHistory.length - 1].finalSolution = data.final_solution;
       chatHistory[chatHistory.length - 1].sessionId = data.session_id;
       saveChatHistory();
     }
     
     // Show download button
     showDownloadButton(data.pdf_download);
   } catch (error) {
     console.error("Error:", error);
     addMessageToChat('assistant', "Sorry, there was an error processing your answers.", 'bot-message');
   } finally {
     showLoading(false);
   }
 }

 // Show download button for report
 function showDownloadButton(pdfUrl = null) {
   if (pdfUrl) {
     downloadBtn.onclick = () => window.open(pdfUrl, '_blank');
   } else if (currentSessionId) {
     downloadBtn.onclick = () => window.open(`http://localhost:5009/download/pdf/${currentSessionId}`, '_blank');
   } else {
     downloadBtn.onclick = downloadTextReport;
   }
   
   reportSection.style.display = 'block';
 }

 // Download text report
 function downloadTextReport() {
   let reportContent = "=== CureBot Medical Consultation Report ===\n\n";
   reportContent += `Generated: ${new Date().toLocaleString()}\n\n`;
   
   chatHistory.forEach((item, index) => {
     reportContent += `[${new Date(item.timestamp).toLocaleTimeString()}] ${item.type === 'image' ? 'IMAGE ANALYSIS' : 'TEXT QUERY'}\n`;
     reportContent += `You: ${item.query}\n`;
     reportContent += `CureBot: ${item.response || item.finalSolution || 'No response recorded'}\n\n`;
   });

   const blob = new Blob([reportContent], { type: 'text/plain' });
   const url = URL.createObjectURL(blob);
   const a = document.createElement('a');
   a.href = url;
   a.download = `curebot_report_${new Date().toISOString().slice(0, 10)}.txt`;
   document.body.appendChild(a);
   a.click();
   document.body.removeChild(a);
   URL.revokeObjectURL(url);
 }

 // Speech recognition
 function startSpeechRecognition() {
   const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
   if (!SpeechRecognition) {
     addMessageToChat('assistant', "Speech recognition not supported in your browser.", 'bot-message');
     return;
   }

   const recognition = new SpeechRecognition();
   recognition.lang = "en-US";
   recognition.interimResults = true;
   
   queryInput.placeholder = "Listening...";
   
   recognition.onresult = (event) => {
     const transcript = event.results[event.resultIndex][0].transcript;
     queryInput.value = transcript;

     if (event.results[event.resultIndex].isFinal) {
       askQuery();
       queryInput.placeholder = "Ask a medical question or describe symptoms...";
     }
   };
   
   recognition.onerror = (event) => {
     console.error("Speech recognition error", event.error);
     queryInput.placeholder = "Ask a medical question or describe symptoms...";
     addMessageToChat('assistant', "Speech recognition error. Please try typing instead.", 'bot-message');
   };
   
   recognition.start();
 }

 // Chat history functions
 function saveChatHistory() {
   localStorage.setItem("chatHistory", JSON.stringify(chatHistory));
   updateChatHistory();
 }

 function updateChatHistory() {
   chatHistoryContainer.innerHTML = '';
   
   // Show most recent first
   chatHistory.slice().reverse().forEach((item, index) => {
     const originalIndex = chatHistory.length - 1 - index;
     const historyItem = document.createElement('div');
     historyItem.className = 'history-item';
     historyItem.innerHTML = `
       <div class="history-item-content">
         <i class="fas ${item.type === 'image' ? 'fa-image' : 'fa-comment-alt'}"></i>
         <div class="history-item-text" title="${item.query}">
           ${item.query.length > 25 ? item.query.substring(0, 25) + '...' : item.query}
         </div>
       </div>
       <div class="history-item-actions">
         <button onclick="loadChatResponse(${originalIndex})" title="View">
           <i class="fas fa-eye"></i>
         </button>
         <button onclick="deleteChatResponse(${originalIndex})" title="Delete">
           <i class="fas fa-trash-alt"></i>
         </button>
       </div>
     `;
     chatHistoryContainer.appendChild(historyItem);
   });
 }

 function loadChatResponse(index) {
   if (index < 0 || index >= chatHistory.length) return;
   
   // Clear current chat
   chatBox.innerHTML = '';
   welcomeMessage.style.display = 'none';
   
   const item = chatHistory[index];
   currentSessionId = item.sessionId || null;
   
   // Recreate the chat
   if (item.type === 'image') {
     // Create a new File object from the data URL if needed
     addMessageToChat('user', 'Uploaded medical image', 'user-message');
     if (item.query !== 'Medical image analysis') {
       addMessageToChat('user', `Analysis request: ${item.query}`, 'user-message');
     }
   } else {
     addMessageToChat('user', item.query, 'user-message');
   }
   
   addMessageToChat('assistant', item.response || item.finalSolution || "No response available", 'bot-message');
   
   // Show download button if available
   if (item.sessionId || item.finalSolution) {
     showDownloadButton();
   }
   
   // Close sidebar on mobile
   if (window.innerWidth <= 768) {
     toggleSidebar();
   }
 }

 function deleteChatResponse(index) {
   if (index < 0 || index >= chatHistory.length) return;
   
   chatHistory.splice(index, 1);
   saveChatHistory();
   
   // If we're currently viewing the deleted chat, start a new one
   if (chatBox.innerHTML.includes(chatHistory[index]?.query)) {
     startNewChat();
   }
 }

 // Start a new chat session
 function startNewChat() {
   chatBox.innerHTML = '';
   currentSessionId = null;
   reportSection.style.display = 'none';
   welcomeMessage.style.display = 'block';
   chatBox.appendChild(welcomeMessage);
   chatBox.scrollTop = chatBox.scrollHeight;
 }