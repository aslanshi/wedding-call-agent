# Ada Voice Assistant

A voice assistant powered by Azure OpenAI, Twilio, and FastAPI that can tell dad jokes, provide cooking inspiration, and search for news using the Tavily API.

## Features

- 🎭 Interactive voice conversations using Azure OpenAI
- 🔊 Real-time audio streaming via Twilio Media Streams
- 🤖 Three main capabilities:
  - Tell dad jokes
  - Provide cooking inspiration
  - Search and summarize recent news using Tavily API
- 🎙️ Natural conversation with voice interruption support
- 📝 Session-based conversation tracking

## Prerequisites

- Python 3.8+
- Azure OpenAI API access
- Twilio account
- Tavily API key
- ngrok or similar tool for local development

## Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint
AZURE_OPENAI_API_KEY=your_azure_openai_api_key
TAVILY_API_KEY=your_tavily_api_key
PORT=5050  # Optional, defaults to 5050
```

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Application

1. Start the FastAPI server:
```bash
python main.py
```

2. Expose your local server using ngrok or similar:
```bash
ngrok http 5050
```

3. Configure your Twilio phone number's voice webhook to point to your exposed URL at the `/incoming-call` endpoint.

## Architecture

- `main.py`: Core FastAPI application with WebSocket handlers and Twilio integration
- `tools.py`: Implements the Tavily search functionality
- Voice processing using Azure OpenAI's real-time API
- WebSocket-based audio streaming between Twilio and Azure OpenAI

## Contributing

Feel free to open issues or submit pull requests for any improvements.

## License

[Add your preferred license]

## Credits

Created by Aslan Shi
