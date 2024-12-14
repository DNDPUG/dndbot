import os
from dotenv import load_dotenv
from server_lookup import server_lookup
import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord import Embed
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import datetime
import logging
import asyncio
import re  # Import re to use regex for cleaning up the realm input
from fuzzywuzzy import process # To match realm names that are incorrectly spelled

# Load environment variables from dndbot.env
load_dotenv(dotenv_path='dndbot.env')

# Set up logging
logging.basicConfig(filename='bot_errors.log', level=logging.ERROR)

# Environment variables
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME')
GOOGLE_WORKSHEET = os.getenv('GOOGLE_WORKSHEET')
OAUTH_URL = os.getenv('OAUTH_URL')
CHARACTER_URL = os.getenv('CHARACTER_URL')
MYTHIC_PROFILE_URL = os.getenv('MYTHIC_PROFILE_URL')

# Set up Discord bot
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_APPLICATION_CREDENTIALS, scope)
client = gspread.authorize(creds)
spreadsheet = client.open(GOOGLE_SHEET_NAME)
worksheet = spreadsheet.worksheet(GOOGLE_WORKSHEET)

# Function to look up the correct realm name using server_lookup
def sanitize_realm(realm_name):
    standardized_realm = ' '.join(word.capitalize() for word in realm_name.split())
    
    # Attempt to find the exact match first
    if standardized_realm in server_lookup:
        return server_lookup[standardized_realm], standardized_realm

    # If not found, try fuzzy matching
    try:
        best_match, score = process.extractOne(standardized_realm, server_lookup.keys())
        if score > 80:  # Choose a confidence threshold
            correct_name = best_match
            sanitized_version = server_lookup[best_match]
            return sanitized_version, correct_name
    except Exception as e:
        logging.error(f"Unexpected error during fuzzy matching: {e}")
        return None, None  # Return None if no close match is found

# Blizzard API setup
def get_access_token():
    try:
        response = requests.post(
            OAUTH_URL,
            data={'grant_type': 'client_credentials'},
            auth=(CLIENT_ID, CLIENT_SECRET)
        )
        response.raise_for_status()  # Raise an error if the request fails
        return response.json()['access_token']
    except requests.RequestException as e:
        logging.error(f"Error obtaining access token for client_id {CLIENT_ID[:4]}** with endpoint {OAUTH_URL}: {e}")
        return None

def get_character_data(realm, character_name, access_token):
    sanitized_realm, correct_realm_name = sanitize_realm(realm)  # Lookup the sanitized version from the dictionary

    # If the realm cannot be found, return None for all fields
    if sanitized_realm is None:
        logging.warning(f"Sanitized realm not found for: {realm}")
        return None, None, None, None, None # Return None for all fields

    # Format URLs using the sanitized realm and character name
    character_url = CHARACTER_URL.format(realm=sanitized_realm, character_name=character_name)
    mythic_profile_url = MYTHIC_PROFILE_URL.format(realm=sanitized_realm, character_name=character_name)

    logging.info(f"Fetching character data for {character_name} from URL: {character_url}")

    headers = {'Authorization': f'Bearer {access_token}'}

    # Retrieve character data
    response = requests.get(character_url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        # Logging for character data
        logging.info(f"Character data retrieved successfully for {character_name} in {sanitized_realm}")

        character_class = data.get('character_class', {}).get('name')
        item_level = data.get('equipped_item_level')

        # Get Mythic+ rating and highest key
        logging.info(f"Fetching mythic profile for {character_name} from URL: {mythic_profile_url}")
        mythic_response = requests.get(mythic_profile_url, headers=headers)
        if mythic_response.status_code == 200:
            mythic_data = mythic_response.json()
            mythic_plus_rating = mythic_data.get('mythic_rating', {}).get('rating', 'N/A')
            # Extract the highest key level completed from best_runs
            best_runs = mythic_data.get('best_runs', {})
            highest_key = max(run.get('keystone_level', 0) for run in best_runs) if best_runs else 'N/A'

            return character_class, item_level, mythic_plus_rating, highest_key, correct_realm_name
        
        logging.error(f"Failed to fetch Mythic+ profile for {character_name}. Status {mythic_response.status_code} Content: {mythic_response.content}")
    else:
        logging.error(f"Error retrieving character data for {character_name}-{sanitized_realm}: Status {response.status_code} Content: {response.content}")
    return None, None, None, None, correct_realm_name

def remove_registration(character_name, realm, discord_name):
    # Read all records in the sheet
    records = worksheet.get_all_records()
    removed_sheet = spreadsheet.worksheet("Removed Signups")
    
    for index, record in enumerate(records):
        if (record['Character'] == character_name and
            record['Realm'] == realm and
            record['Discord User'] == discord_name):
            try:
                # Add to Removed Signups sheet
                removed_sheet.append_row([
                    datetime.datetime.now().strftime('%m/%d/%Y %H:%M:%S'),  # Timestamp
                    record.get('Character', 'N/A'),
                    record.get('Class', 'N/A'),
                    record.get('Discord User', 'N/A'),
                    record.get('Realm', 'N/A'),
                    record.get('Role', 'N/A')
                ])
                logging.info(f"Appended removed record for {character_name}-{realm} to 'Removed Signups'.")
                
                # Remove from the main sheet
                worksheet.delete_rows(index + 2)  # +2 because get_all_records() is 0-indexed, and row 1 is the header
                return True
            except Exception as e:
                logging.error(f"Error deleting row for {character_name}-{realm}: {e}")
                return False
    # Log if the character wasn't found for removal
    logging.warning(f"No matching record found for removal: {character_name}-{realm} by {discord_name}.")
    return False

def check_user_registration(discord_name):
    records = worksheet.get_all_records()
    for record in records:
        if record['Discord User'] == discord_name:
            return record
    return None

#Sign up buttons
class DndOptionsView(discord.ui.View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label='Sign Up for M+ Event', style=discord.ButtonStyle.success)
    async def signup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Defer the response to avoid webhook timeout
        await interaction.response.defer(ephemeral=True)

        # Check if the user is already registered
        existing_record = check_user_registration(interaction.user.name)
        if existing_record:
            character_name = existing_record['Character']
            realm = existing_record['Realm']
            
            # Create Yes/No buttons
            class ConfirmEditView(discord.ui.View):
                @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
                async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.clear_items()
                    if not interaction.response.is_done():
                        await interaction.response.edit_message(view=self)
                        
                        # Remove existing registration
                        if remove_registration(existing_record['Character'], existing_record['Realm'], interaction.user.name):
                            await interaction.followup.send(
                                f"Your registration for **{existing_record['Character']}**-**{existing_record['Realm']}** has been successfully removed.",
                                ephemeral=True
                            )
                            # Add a delay before prompting for a new registration
                            await asyncio.sleep(2)
                            await interaction.followup.send("Please click below to start a new registration:", view=DndOptionsView(), ephemeral=True)
                        else:
                            await interaction.followup.send(
                                "An error occurred while trying to remove your registration. Please try again.",
                                ephemeral=True
                            )

                @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
                async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.clear_items()
                    await interaction.response.edit_message(view=self)
                    await interaction.followup.send("Thanks for registering!", ephemeral=True)
            
            await interaction.followup.send(f"Looks like you are already signed up with {character_name}-{realm}! Do you want to remove this character and edit your registration?", view=ConfirmEditView(), ephemeral=True)
        else:
            await start_registration(interaction, deferred=True)
    
    @discord.ui.button(label='Remove Signup', style=discord.ButtonStyle.danger)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        existing_record = check_user_registration(interaction.user.name)
        if existing_record:
            await interaction.followup.send(
                f"You are currently signed up with {existing_record['Character']}-{existing_record['Realm']}, do you want to remove this registration?",
                ephemeral=True
            )

            class ConfirmRemoveView(discord.ui.View):
                @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
                async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.clear_items()
                    if not interaction.response.is_done():
                        await interaction.response.edit_message(view=self)
                        if remove_registration(existing_record['Character'], existing_record['Realm'], interaction.user.name):
                            await interaction.followup.send(
                                f"Your registration for **{existing_record['Character']}**-**{existing_record['Realm']}** has been removed.",
                                ephemeral=True
                            )
                        else:
                            await interaction.followup.send(
                                "An error occurred while trying to remove your registration. Please try again.",
                                ephemeral=True
                            )

                @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
                async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.clear_items()
                    await interaction.response.edit_message(view=self)
                    await interaction.followup.send("Your registration has not been removed.", ephemeral=True)

            await interaction.followup.send("Please confirm if you want to remove your registration:", view=ConfirmRemoveView(), ephemeral=True)
        else:
            await interaction.followup.send('No registration found for you.', ephemeral=True)

    @discord.ui.button(label='M+ Event Info', style=discord.ButtonStyle.secondary, custom_id="mplus_info")
    async def event_info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        link = "https://discord.com/channels/810543579856502834/1282792395381018696/1283756210897682462"
        records = worksheet.get_all_records()
        signup_count = len(records)
        await interaction.followup.send(
            f"The number of people who have signed up for this week's event: {signup_count}\n"
            f"For more information, visit this post: {link}", ephemeral=True
        )

# Role buttons
class RoleView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.selected_role = None

    @discord.ui.button(label='DPS', style=discord.ButtonStyle.primary)
    async def dps_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.selected_role = 'DPS'
        await interaction.response.send_message('You selected DPS!', ephemeral=True, delete_after=15)
        self.stop()

    @discord.ui.button(label='Healer', style=discord.ButtonStyle.primary)
    async def healer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.selected_role = 'Healer'
        await interaction.response.send_message('You selected Healer!', ephemeral=True, delete_after=15)
        self.stop()

    @discord.ui.button(label='Tank', style=discord.ButtonStyle.primary)
    async def tank_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.selected_role = 'Tank'
        await interaction.response.send_message('You selected Tank!', ephemeral=True, delete_after=15)
        self.stop()

# Key Range buttons
class KeyRangeView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.selected_key_range = None

    @discord.ui.button(label='Heroics (Weathered)', style=discord.ButtonStyle.primary)
    async def heroics_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.selected_key_range = 'Heroics (Weathered)'
        await interaction.response.send_message('You selected Heroics (Weathered)!', ephemeral=True, delete_after=15)
        self.stop()

    @discord.ui.button(label='0-3 (Carved)', style=discord.ButtonStyle.primary)
    async def zero_to_three_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.selected_key_range = '0-3 (Carved)'
        await interaction.response.send_message('You selected 0-3 (Carved)!', ephemeral=True, delete_after=15)
        self.stop()

    @discord.ui.button(label='4-5 (Runed - Lower)', style=discord.ButtonStyle.primary)
    async def four_to_five_lower_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.selected_key_range = '4-5 (Runed - Lower)'
        await interaction.response.send_message('You selected 4-5 (Runed - Lower)!', ephemeral=True, delete_after=15)
        self.stop()

    @discord.ui.button(label='6-7 (Runed - Upper)', style=discord.ButtonStyle.primary)
    async def six_to_seven_upper_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.selected_key_range = '6-7 (Runed - Upper)'
        await interaction.response.send_message('You selected 6-7 (Runed - Upper)!', ephemeral=True, delete_after=15)
        self.stop()

    @discord.ui.button(label='8+ (Gilded)', style=discord.ButtonStyle.primary)
    async def eight_plus_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.selected_key_range = '8+ (Gilded)'
        await interaction.response.send_message('You selected 8+ (Gilded)!', ephemeral=True, delete_after=15)
        self.stop()

# Initialize and define Modal
class RegistrationModal(discord.ui.Modal, title="Registration Form"):
    def __init__(self, signup_date_str):
        super().__init__()

        # Add other fields to the modal
        self.character_name = discord.ui.TextInput(label="Character Name (include special characters)", style=discord.TextStyle.short)
        self.realm = discord.ui.TextInput(label="Realm (double check your realm!)", style=discord.TextStyle.short)
        self.special_requests = discord.ui.TextInput(label="Special Requests (optional)", style=discord.TextStyle.long, required=False)

        # Add the inputs to the modal
        self.add_item(self.character_name)
        self.add_item(self.realm)
        self.add_item(self.special_requests)
        
    async def on_submit(self, interaction: discord.Interaction):
        messages_to_delete = []
        
        # Sanitize the realm name for Blizzard API queries by removing apostrophes and hyphens
        sanitized_realm, correct_realm_name = sanitize_realm(self.realm.value.lower())

        # Capitalize the first letter of the character name for Google Sheets entry
        character_name_cap = self.character_name.value.capitalize()

        # Get access token
        access_token = get_access_token()

        # Get character data (class, item level, mythic+ rating, highest key)
        character_class, item_level, mythic_plus_rating, highest_key, correct_realm_name = get_character_data(sanitized_realm, self.character_name.value.lower(), access_token)

        if character_class is None:
            character_class, item_level, mythic_plus_rating, highest_key = "N/A", "N/A", "N/A", "N/A"

        # Store basic character info and send a confirmation message
        self.character_info = {
            'character_name': character_name_cap,
            'realm': correct_realm_name,
            'character_class': character_class,
            'item_level': item_level,
            'mythic_plus_rating': mythic_plus_rating,
            'highest_key': highest_key,
            'submission_time': datetime.datetime.now().strftime('%m/%d/%Y %H:%M:%S'),
            'discord_user': interaction.user.name
        }

        role_message = await interaction.response.send_message(
            f'Thank you, {interaction.user.name}! Your submission of {character_name_cap}-{correct_realm_name}, {character_class}. has been recorded. Next, please select your role.',
            ephemeral=True, delete_after=30
        )
        if role_message:
            messages_to_delete.append(role_message)

        # Prompt for role selection after the modal
        role_view = RoleView()
        role_prompt_message = await interaction.followup.send('Please select your Role:', view=role_view, ephemeral=True)
        if role_prompt_message:
            messages_to_delete.append(role_prompt_message)
        await role_view.wait()

        # Now prompt for key range selection
        key_range_view = KeyRangeView()
        key_range_prompt_message = await interaction.followup.send('Please select your Key Range:', view=key_range_view, ephemeral=True)
        if key_range_prompt_message:
            messages_to_delete.append(key_range_prompt_message)
        await key_range_view.wait()

        # Now, update the Google Sheet after gathering all inputs
        try:
            # Prepare row data for Google Sheets
            row_data = [
                self.character_info['submission_time'],
                self.character_info['character_name'],
                self.character_info['character_class'],
                self.character_info['discord_user'],
                self.character_info['realm'],
                role_view.selected_role,
                self.character_info['item_level'],
                self.character_info['mythic_plus_rating'],
                self.character_info['highest_key'],
                key_range_view.selected_key_range,
                "",  # Empty column
                self.special_requests.value
            ]

            # Append to Google Sheets
            worksheet.append_row(row_data)
            logging.info(f"Successfully appended row to Google Sheets for {self.character_info['character_name']}-{self.character_info['realm']}")
        except Exception as e:
            logging.error(f"Error appending row to Google Sheets for {self.character_info['character_name']}-{self.character_info['realm']}: {e}")
            error_message_sheet = await interaction.followup.send('There was an error recording your registration. Please try again later.', ephemeral=True)
            if error_message_sheet:
                messages_to_delete.append(error_message_sheet)
            return

        final_confirmation = await interaction.followup.send(
            f'Thank you, {interaction.user.name}! Your registration has been completed with your {role_view.selected_role} {character_class} for keys {key_range_view.selected_key_range}. You are ilvl: {item_level}, and your Mythic+ rating is {mythic_plus_rating}. We will also pull an updated rating closer to the event date.',
            ephemeral=True
        )
        if final_confirmation:
            messages_to_delete.append(final_confirmation)
        
        # Delete all ephemeral messages manually after a delay
        await asyncio.sleep(5)  # Optional delay if you want them to read the messages briefly
        for msg in messages_to_delete:
            if msg:  # Check if the message is not None
                try:
                    await msg.delete()
                except discord.NotFound:
                    logging.warning(f"Message {msg.id} was not found for deletion.")

# Define StartRegistrationView outside of start_registration
class StartRegistrationView(discord.ui.View):
    def __init__(self, signup_date_str):
        super().__init__()
        self.signup_date_str = signup_date_str
        
    @discord.ui.button(label="Start Registration", style=discord.ButtonStyle.primary)
    async def start_registration_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
        # Pass the signup_date_str to RegistrationModal
        await button_interaction.response.send_modal(RegistrationModal(self.signup_date_str))

async def start_registration(interaction: discord.Interaction, deferred=False):
    # Determine the upcoming Saturdays date
    current_date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5)))  # EST
    this_saturday = current_date + datetime.timedelta((5 - current_date.weekday()) % 7)
    next_saturday = this_saturday + datetime.timedelta(weeks=1)
    signup_cutoff = datetime.datetime.combine(current_date.date(), datetime.time(18, 0), tzinfo=datetime.timezone(datetime.timedelta(hours=-5)))
    messages_to_delete = []  # Store messages for deletion later

    if current_date >= signup_cutoff:
        signup_date_str = next_saturday.strftime('%b %d')
    else:
        signup_date_str = this_saturday.strftime('%b %d')

    # Create an embed to show the event information
    embed = Embed(title="Key Event Information",
                  description=f"You are signing up for the key event on **{signup_date_str}**.",
                  color=0x00ff00)
                  
    # Check if the interaction was already responded to or deferred
    if not deferred:
        # Send a modal as the first interaction response
        await interaction.response.send_modal(RegistrationModal(signup_date_str))
        # Send event information as an embed after submitting the modal
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        # Since it was deferred, send a follow up message
        start_reg_message = await interaction.followup.send("Click the button below to start the registration process:", view=StartRegistrationView(signup_date_str), ephemeral=True)
        if start_reg_message:
            messages_to_delete.append(start_reg_message)

    submission_time = datetime.datetime.now().strftime('%m/%d/%Y %H:%M:%S')

    await asyncio.sleep(10)  
    for msg in messages_to_delete:
        if msg:  # Check if the message is not None
            try:
                await msg.delete()
            except discord.NotFound:
                logging.warning(f"Message {msg.id} was not found for deletion.")

@tasks.loop(time=datetime.time(hour=18, minute=0, tzinfo=datetime.timezone(datetime.timedelta(hours=-5))))
async def schedule_signup_date_change():
    current_date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5)))  # EST
    cutoff_date = current_date.strftime('%m-%d-%Y')
    
    try:
        # Rename current sheet to include cutoff date
        old_title = worksheet.title
        new_title = f"{old_title} - Cutoff {cutoff_date}"
        worksheet.update_title(new_title)
        logging.info(f"Renamed sheet to: {new_title}")

        # Get the header row
        header_row = worksheet.row_values(1)

        # Create a new worksheet for the next registration period
        new_worksheet = spreadsheet.add_worksheet(title="General Info", rows="100", cols="20")
        new_worksheet.append_row(header_row)
        logging.info("Created new worksheet titled 'General Info' with header row copied.")

        # Update the global worksheet reference
        global worksheet
        worksheet = new_worksheet

    except Exception as e:
        logging.error(f"Error during weekly sheet management: {e}")
    
async def update_character_data():
    records = worksheet.get_all_records()
    access_token = get_access_token()
    for record in records:
        character_name = record['Character']
        realm = sanitize_realm(record['Realm'].lower())
        character_class, item_level, mythic_plus_rating, highest_key = get_character_data(realm, character_name.lower(), access_token)
        if character_class:
            worksheet.update_cell(record['Row'], 8, character_class)
            worksheet.update_cell(record['Row'], 9, item_level)
            worksheet.update_cell(record['Row'], 10, mythic_plus_rating)
            worksheet.update_cell(record['Row'], 11, highest_key)

# Console information, shows how many commands the bot has and what the botname is
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s) to Discord!")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    
    # Start weekly management task
    if not weekly_sheet_management.is_running():
        weekly_sheet_management.start()

    print(f'Logged in as {bot.user.name}')

# Very first text that calls sign up, removal and info buttons
@bot.tree.command(name="dnd", description="Register for a DnD event")
async def dnd(interaction: discord.Interaction):
    await interaction.response.send_message('Please choose an option:', view=DndOptionsView(), ephemeral=True)

# Run the bot
bot.run(BOT_TOKEN)
