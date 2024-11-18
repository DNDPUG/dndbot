# DnD M+ Event Registration Bot

## Overview
This bot is designed for DnD Mythic+ event registration on Discord. It interacts with users to gather character information and uses Google Sheets for storing event registrations. The bot also interacts with Blizzard's WoW Armory API to validate character information.

### Features
- Register for Mythic+ events through Discord.
- Remove existing registrations and start a new one.
- Collect character details, item level, Mythic+ rating, and more.
- Uses fuzzy matching to correct minor typos in realm names.
- Stores registration information in Google Sheets.

### Requirements
- Python 3.9 or later.
- `discord.py` library.
- `gspread` and `oauth2client` for Google Sheets interaction.
- `fuzzywuzzy` for fuzzy matching of realm names.

### Setup Instructions
1. Clone the repository.
2. Install dependencies using:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a .env file with the following details:
   - DISCORD_BOT_TOKEN
   - CLIENT_ID
   - CLIENT_SECRET
   - GOOGLE_APPLICATION_CREDENTIALS
   - GOOGLE_SHEET_NAME
   - GOOGLE_WORKSHEET
   - OAUTH_URL
   - CHARACTER_URL
   - MYTHIC_PROFILE_URL
4. Run the bot:
   ```bash
   python dndmplusbot.py
   ```

### Commands
- `/dnd`: Opens options for registration, removal, or event information.

### Usage Instructions
- **Sign Up**: Users can register for the event by entering character details.
- **Remove Registration**: Users can remove existing registrations and register again.
- **Mythic+ Event Info**: Displays the count of registered participants and a link to more details.

### Version History
- **1.0**: Initial bot implementation with basic registration and removal features.
- **1.1**: 
  - Added fuzzy matching for realm names to correct minor typos automatically.
  - Improved registration process by adding a 2-second delay between removing a previous registration and prompting for a new one, ensuring a smoother experience.
  - Removed the "Proceed Anyway" button for streamlined user experience during re-registration.
  - Rearranged Google Sheets columns for better organization:
    - Added a filter column between Key Range and Special Requests to facilitate easier data management.
  - Enhanced error handling to ensure the bot checks if a response is already completed before sending follow-up messages.
  - Improved logging with more context on errors during API responses and Google Sheets interactions.
  - Implemented version control, with this release being labeled as version 1.1. Previous features and functionality are considered version 1.0.
