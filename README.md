# Ada Voice Assistant

A voice assistant powered by Azure OpenAI, Twilio, and FastAPI that can give my wedding guests a hint to the Bingo game on the day of the event, as well as offering some cool dad jokes (cause why not).

## Features

- 🎭 Interactive voice conversations using Azure OpenAI
- 🔊 Real-time audio streaming via Twilio Media Streams
- 🤖 Two main capabilities:
  - Give my guests a hint to the Bingo game that we're about to play on the day of my wedding
  - Offer to repeat the hint or dad jokes if guests are calling back (use Make.com to store caller information and chat history in a Google Spreadsheet)
- 🎙️ Natural conversation with voice interruption support
- 📝 Session-based conversation tracking

## Prerequisites

- Python 3.8+
- Azure OpenAI API access
- Twilio account
- Tavily API key (not used in this project)
- ngrok or similar tool for local development (not used in this project)

## Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint
AZURE_OPENAI_API_KEY=your_azure_openai_api_key
MAKE_WEBHOOK_URL=your_make_dot_com_webhook_url
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

3. Configure your Twilio phone number's voice webhook to point to your exposed URL at the `/incoming-call` endpoint. (On Twilio account website)

## Architecture

- `main.py`: Core FastAPI application with WebSocket handlers and Twilio integration
- `tools.py`: Implements the Tavily search functionality (not used in this project)
- Voice processing using Azure OpenAI's real-time API
- WebSocket-based audio streaming between Twilio and Azure OpenAI

## Contributing

Feel free to open issues or submit pull requests for any improvements.

## License

[Add your preferred license]

## Credits

Created by Aslan Shi
