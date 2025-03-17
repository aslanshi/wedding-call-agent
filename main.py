import os
import json
import time
import base64
import aiohttp
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect, Say, Stream
from dotenv import load_dotenv

load_dotenv()

from tools import tavily_search_tool_json, tavily_search

# Configuration
# OPENAI_ENDPOINT_URL = os.getenv("OPENAI_ENDPOINT_URL")
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")
PORT = int(os.getenv("PORT", 5050))
SYSTEM_MESSAGE = """\
You are Ada, a helpful wedding assistant created by A (groom) for his and B's (bride) wedding on June 27th, 2025.

Your purpose: Help guests participate in a special wedding day game. This game encourages guest interaction by requiring them to find answers to 3 questions by talking to other guests who share special memories with the couple.

Your specific task: When guests call before the wedding, provide them with one preview question and hint they'll encounter during the game:
- Question: "What's the city name where the groom's college is located?"
- Hint: "Find someone who's been working in Mexico."

Conversation flow:
1. Warmly greet guests and thank them for sharing special moments with A and B
2. Briefly explain how the game will work on the wedding day
3. Share the question and hint
4. If they've called before (you'll be provided their name and call history), greet them by name and offer to repeat the information
5. Offer a funny dad joke if they're interested

Response guidelines:
- Only answer questions about the game and provide the designated hint
- For game details you don't know, politely direct guests to the couple
- For other wedding information, refer them to the wedding website
- Maintain a positive, quick-paced conversation style
- Include appropriate humor when fitting\
"""
VOICE = "alloy"
LOG_EVENT_TYPES = [
    "error",
    "response.content.done",
    "rate_limits.updated",
    "response.done",
    "input_audio_buffer.committed",
    "input_audio_buffer.speech_stopped",
    "input_audio_buffer.speech_started",
    "session.created",
]
SHOW_TIMING_MATH = False

# Session management - store session data
sessions = dict()

app = FastAPI()

if not AZURE_OPENAI_API_KEY:
    raise ValueError(
        "Missing the Azure OpenAI API key. Please set it in the .env file."
    )

if not AZURE_OPENAI_ENDPOINT:
    raise ValueError(
        "Missing the Azure OpenAI Endpoint URL. Please set it in the .env file."
    )


@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}


@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    # <Say> punctuation to improve text-to-speech flow
    response.say("Please wait while we connect your call to the AI voice assistant.")
    response.pause(length=1)
    response.say(
        "Connected!"
    )
    host = request.url.hostname
    connect = Connect()
    stream = connect.stream(url=f"wss://{host}/media-stream")

    # Collect call info
    form_data = await request.form()
    caller_number = form_data.get("From", "Unknown")
    session_id = form_data.get("CallSid")
    print(f"Caller Number: {caller_number}")
    print(f"Session Id (CallSid): {session_id}")

    first_message = (
        "Greet the user with 'Hello there! Welcome to Aslan and Bingru's wedding celebration! "
        "Thank you so much for being an important part of their journey together. "
        "I am Ada, an AI voice assistant created by Aslan. "
        "I'm here to tell you about a fun game you'll get to play on the wedding day! "
        "May I first know your name, please?'"
    )

    # Send the caller's number to Make.com webhook to get a personalized first message
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                MAKE_WEBHOOK_URL,
                headers={"Content-Type": "application/json"},
                json={
                    "route": "1",
                    "data1": caller_number,
                    "data2": "",  # Extra data (not used here)
                },
            ) as webhook_response:

                print(f"Webhook response status: {webhook_response.status}")

                if webhook_response.ok:
                    webhook_response_text = await webhook_response.text()
                    print(f"Webhook response: {webhook_response_text}")
                    try:
                        webhook_response_data = json.loads(webhook_response_text)
                        if webhook_response_data and webhook_response_data.get(
                            "firstMessage"
                        ):
                            first_message = webhook_response_data["firstMessage"]
                            print("Parsed firstMessage from Make.com:", first_message)
                    except json.JSONDecodeError as parse_error:
                        print(
                            "Error parsing webhook response:", parse_error
                        )  # Log any errors while parsing the response
                        first_message = (
                            webhook_response_text.strip()
                        )  # Use the plain text response if parsing fails
                else:
                    error_msg = (
                        f"Failed to send data to webhook: {webhook_response.reason}"
                    )
                    print(error_msg)

    except Exception as error:
        print(f"Error sending data to webhook: {str(error)}")

    # Update sessions
    session = {
        "transcript": "",
        "caller_number": caller_number,
        "first_message": first_message,
    }
    sessions.update({session_id: session})

    # Add customer parameters
    # TODO: not actually used in the later functions
    # as long as later it could locate the correct session
    stream.parameter(name="caller_number", value=caller_number)
    stream.parameter(name="first_message", value=first_message)
    response.append(connect)

    return HTMLResponse(content=str(response), media_type="application/xml")


@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and Azure OpenAI."""
    print("Client connected")
    await websocket.accept()

    # Use Twilio's CallSid as the session ID or create a new one based on the timestamp
    # TODO: headers don't contain the call sid, so it always uses timestamp
    # which results in creating a session overwritting the previous one every time
    # and thus losing caller number and first message
    # currently skipping this retriving Call Sid again during the `start` event
    session_id = (
        websocket.headers.get("x-twilio-call-sid") or f"session_{int(time.time())}"
    )

    # Get the session data or create a new session
    # Currently not used as explained above
    session = sessions.get(session_id) or {"transcript": ""}
    # sessions.update({session_id: session})

    async with websockets.connect(
        AZURE_OPENAI_ENDPOINT,
        extra_headers={
            "api-key": AZURE_OPENAI_API_KEY,
        },
    ) as openai_ws:
        await initialize_session(openai_ws)

        # Connection specific state
        stream_sid = None
        latest_media_timestamp = 0
        last_assistant_item = None
        mark_queue = []
        response_start_timestamp_twilio = None

        async def send_first_message(first_message):
            """Send first message using webhook results"""
            print("Sending first message:", first_message)
            await openai_ws.send(json.dumps(first_message))
            await openai_ws.send(json.dumps({"type": "response.create"}))

        async def receive_from_twilio():
            """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
            nonlocal stream_sid, latest_media_timestamp, session, session_id
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data["event"] == "media" and openai_ws.open:
                        latest_media_timestamp = int(data["media"]["timestamp"])
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data["media"]["payload"],
                        }
                        await openai_ws.send(json.dumps(audio_append))

                    elif data["event"] == "start":
                        stream_sid = data["start"]["streamSid"]
                        print(f"Incoming stream has started {stream_sid}")
                        response_start_timestamp_twilio = None
                        latest_media_timestamp = 0
                        last_assistant_item = None

                        # Get call sid
                        call_sid = data["start"]["callSid"]
                        session_id = call_sid
                        session = sessions[session_id]

                        # Prepare the first message
                        first_message = session.get(
                            "first_message",
                            "Greet the user with 'Hello there! Welcome to Aslan and Bingru's wedding celebration! Thank you so much for being an important part of their journey together. I am Ada, an AI voice assistant created by Aslan. I'm here to tell you about a fun game you'll get to play on the wedding day! May I first know your name, please?'",
                        )
                        queued_first_message = {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "user",
                                "content": [
                                    {"type": "input_text", "text": first_message}
                                ],
                            },
                        }
                        await send_first_message(queued_first_message)
                        del queued_first_message

                    elif data["event"] == "mark":
                        if mark_queue:
                            mark_queue.pop(0)
            except WebSocketDisconnect:
                print("WebSocketDisconnect exception caught")  # Debug log
                print(f"Client disconnected ({session_id}).")
                print(f"Full transcript ({session_id}):\n{session['transcript']}")
                if openai_ws.open:
                    await openai_ws.close()

                await send_to_webhook(
                    {
                        "route": "2",
                        "data1": session["caller_number"],
                        "data2": session["transcript"],
                    }
                )
                if session_id in sessions:
                    del sessions[session_id]
            except Exception as e:
                print(f"Exception details: {str(e)}")
                if isinstance(e, websockets.exceptions.ConnectionClosed):
                    print("Connection was closed")
                print(f"Client disconnected with error ({session_id}).")
                print("Full Transcript:")
                print(session.get("transcript", ""))
            finally:
                print(f"Full transcript ({session_id}):\n{session['transcript']}")
                try:
                    if openai_ws.open:
                        print("Closing OpenAI WebSocket")
                        await openai_ws.close()

                    await send_to_webhook(
                        {
                            "route": "2",
                            "data1": session["caller_number"],
                            "data2": session["transcript"],
                        }
                    )
                    if session_id in sessions:
                        print(f"Cleaning up session {session_id}")
                        del sessions[session_id]
                except Exception as cleanup_error:
                    print(f"Error during cleanup: {cleanup_error}")

        async def send_to_twilio():
            """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
            nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio, session, session_id
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    if response["type"] in LOG_EVENT_TYPES:
                        print(f"Received event: {response['type']}", response)

                    if (
                        response.get("type") == "response.audio.delta"
                        and "delta" in response
                    ):
                        audio_payload = base64.b64encode(
                            base64.b64decode(response["delta"])
                        ).decode("utf-8")
                        audio_delta = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": audio_payload},
                        }
                        await websocket.send_json(audio_delta)

                        if response_start_timestamp_twilio is None:
                            response_start_timestamp_twilio = latest_media_timestamp
                            if SHOW_TIMING_MATH:
                                print(
                                    f"Setting start timestamp for new response: {response_start_timestamp_twilio}ms"
                                )

                        # Update last_assistant_item safely
                        if response.get("item_id"):
                            last_assistant_item = response["item_id"]

                        await send_mark(websocket, stream_sid)

                    # Trigger an interruption. Your use case might work better using `input_audio_buffer.speech_stopped`, or combining the two.
                    if response.get("type") == "input_audio_buffer.speech_started":
                        print("Speech started detected.")
                        if last_assistant_item:
                            print(
                                f"Interrupting response with id: {last_assistant_item}"
                            )
                            await handle_speech_started_event()

                    # Log agent message
                    if response.get("type") == "response.done":
                        agent_msg = ""
                        response_output = response.get("response", {}).get("output", [])
                        if response_output:
                            content_list = response_output[0].get("content", [])
                            if content_list:
                                agent_msg = content_list[0].get(
                                    "transcript", "Assistant message not found"
                                )
                        else:
                            agent_msg = "Assistant message not found"
                        session["transcript"] += f"\nAgent: {agent_msg}\n"
                        print(f"Agent ({session_id}): {agent_msg}")

                    # Log user message
                    if (
                        response.get("type")
                        == "conversation.item.input_audio_transcription.completed"
                        and "transcript" in response
                    ):
                        user_msg = response.get(
                            "transcript", "User message not found"
                        ).strip()
                        session["transcript"] += f"\nUser: {user_msg}\n"
                        print(f"User ({session_id}): {user_msg}")

                    if response.get("type") == "response.function_call_arguments.done":
                        print(f"Function called: {response}")
                        function_name = response.get("name")
                        function_args = json.loads(response.get("arguments"))
                        call_id = response.get("call_id")

                        user_query = function_args.get("query")

                        if function_name == "tavily_search":
                            try:
                                search_result = await tavily_search(**function_args)
                                if search_result:
                                    search_content = search_result[1]
                                else:
                                    search_content = (
                                        "Sorry, no results found for that question."
                                    )

                                # Send function call result back to OpenAI
                                function_output_event = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "output": search_content,
                                        "call_id": call_id,
                                    },
                                }
                                await openai_ws.send(json.dumps(function_output_event))
                                print(
                                    f"Sent function call result: {function_output_event}"
                                )

                                function_call_response_from_openai = {
                                    "type": "response.create",
                                    "response": {
                                        "modalities": ["text", "audio"],
                                        "instructions": f"Summarize the news and respond to the user's question {user_query} based on this news summary: {search_content}. Be concise and friendly. Do not use bullet points in your response.",
                                    },
                                }
                                await openai_ws.send(
                                    json.dumps(function_call_response_from_openai)
                                )
                            except Exception as e:
                                print(f"Error calling function {function_name}: {e}")
                                await send_error_response(openai_ws)
            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

        async def handle_speech_started_event():
            """Handle interruption when the caller's speech starts."""
            nonlocal response_start_timestamp_twilio, last_assistant_item
            print("Handling speech started event.")
            if mark_queue and response_start_timestamp_twilio is not None:
                elapsed_time = latest_media_timestamp - response_start_timestamp_twilio
                if SHOW_TIMING_MATH:
                    print(
                        f"Calculating elapsed time for truncation: {latest_media_timestamp} - {response_start_timestamp_twilio} = {elapsed_time}ms"
                    )

                if last_assistant_item:
                    if SHOW_TIMING_MATH:
                        print(
                            f"Truncating item with ID: {last_assistant_item}, Truncated at: {elapsed_time}ms"
                        )

                    truncate_event = {
                        "type": "conversation.item.truncate",
                        "item_id": last_assistant_item,
                        "content_index": 0,
                        "audio_end_ms": elapsed_time,
                    }
                    await openai_ws.send(json.dumps(truncate_event))

                await websocket.send_json({"event": "clear", "streamSid": stream_sid})

                mark_queue.clear()
                last_assistant_item = None
                response_start_timestamp_twilio = None

        async def send_mark(connection, stream_sid):
            if stream_sid:
                mark_event = {
                    "event": "mark",
                    "streamSid": stream_sid,
                    "mark": {"name": "responsePart"},
                }
                await connection.send_json(mark_event)
                mark_queue.append("responsePart")

        await asyncio.gather(receive_from_twilio(), send_to_twilio())


async def send_initial_conversation_item(openai_ws):
    """Send initial conversation item if AI talks first."""
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Greet the user with 'Hello there! I am Ada, an AI voice assistant created by Aslan. You can ask me for dad jokes, cooking inspirations and news summary. How can I help you?'",
                }
            ],
        },
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({"type": "response.create"}))


async def initialize_session(openai_ws):
    """Control initial session with OpenAI."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
            "input_audio_transcription": {"model": "whisper-1"},
            # "tools": [
            #     tavily_search_tool_json,
            # ],
            # "tool_choice": "auto",
        },
    }
    print("Sending session update:", json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))

    # Uncomment the next line to have the AI speak first
    # await send_initial_conversation_item(openai_ws)


async def send_error_response(openai_ws):
    """Helper function for sending error responses"""
    await openai_ws.send(
        json.dumps(
            {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "I apologize, but I'm having trouble processing your request right now. Is there anything else I can help you with?",
                },
            }
        )
    )


async def send_to_webhook(payload):
    """Function to send data to the Make.com webhook"""
    # Log the data being sent
    print(f"Sending data to webhook: {json.dumps(payload, indent=2)}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                MAKE_WEBHOOK_URL,
                headers={"Content-Type": "application/json"},
                json=payload,
            ) as response:

                print(f"Webhook response status: {response.status}")

                if response.ok:
                    response_text = await response.text()
                    print(f"Webhook response: {response_text}")
                    return response_text
                else:
                    error_msg = f"Failed to send data to webhook: {response.reason}"
                    print(error_msg)
                    raise Exception(error_msg)

    except Exception as error:
        print(f"Error sending data to webhook: {str(error)}")
        raise


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
