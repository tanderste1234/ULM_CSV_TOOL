# ULM_CSV_TOOL
the replacement for the old query system for ULM
## 🛠️ Prerequisites & Setup for Version 1.3.0
Follow these steps to install the tool.
### 1. Downloading The Exe File

1. Open the `releases` folder in this repository.
2. Click on the `ULMCSVTOOLV1.3.0.exe` file.
3. On the file preview screen, locate the group of 3 buttons in the top-right corner (the first button is labeled **Raw**).
4. Click the 3rd button on the right (the download icon, which shows the tooltip **"Download raw file"** when you hover over it) to save the file to your computer.
5. you should save the tool somewhere easy to get to as you will need to either make a shortcut or have this file on the desktop

> **Note:** `ULMCSVTOOLV1.3.0.exe` is a fully self-contained file. You do not need to install Python, run any command-line scripts, or download additional setup files—just open the file, and you are good to go!
## 💻 Using The Tool for Version 1.3.0
### 1. Selecting The Input and Output Files
1. First you will need to double-click the `ULMCSVTOOLV1.3.0.exe` file to run the tool or if you made a desktop shortcut double-click the shortcut
2. Next you will need to hit the <kbd>Browse...</kbd> button in the program window next to the `input file:` label and after the white input box
3. Navigate to your data file's location using windows file explorer and select the file
> **Note:** the output file will automatically name itself after your input file's name with `_processed.csv` on the end of the original file name if you do not want the output file to be named this way please click the <kbd>Browse...</kbd> button on the end of the input labeled output file and navigate to the place you would like to have your output file then name it whatever you want
### 2. Selecting The Fields
1. The next step is to select what fields you are interested in and enter them in a comma separated list in the columns to keep field
> **Note:** the time field is not automatically kept so if you would like the times kept please remember to add it in this field
2. once you have decided what fields you are interested in and entered them correctly
3. in the next two fields labeled Year Column and Date Column refer to the headers in the column headers for the names of the year and date fields they should be the first two entries you can copy them if you want but make sure to remove any commas or spaces
> **Note:** these column names should be "year" and "day" but refer to the headers if the first 2 headers are different 
### 3. Selecting the Dates
1. the next input is your date format field
2. to choose the date format simply click the diamond next to the desired format 
>  **Note:** the default is YYYY-MM
3. once you select the date format of your preference then please enter a comma separated list of start dates into the field named Start Dates and then a respective list of end dates into the field labeled End Dates please make sure you follow the requirements below when entering dates
> **Important Requirements:** It is important that you make sure to enter an equal amount of start and end dates as the program will not work other wise. If you do not follow the date format you have selected it will not yield correct results. Also please make sure to use dates that are present in the data file you have selected as anything not present in your data file will cause errors if entered.
4. once you have correctly entered the dates hit the <kbd>Start Processing</kbd> button on the bottom left of the window next to the <kbd>Show Debug Window</kbd> button.
> **Note:** the Show debug window button is only for finding problems with the application and you should not need it
### 4. Checking The Output File
1. after the processing is finished there should be a pop up saying the processing completed successfully click the <kbd>okay</kbd> button
2. now open the output file with whatever program you wish and check that your filtered data is there
> **Note:** if you kept the default it will have made the output in the input file folder with `_processed.csv` on the end of it
## 🪛 Troubleshooting:
1. if you ever need to update the backend.py file and you need to pack it into an exe file you need to run this command inside the folder you downloaded the repo to then pull it out of the dist folder and move it into the releases folder and then delete the dist folder and also if you do this remember to update the version numbers the first one is For MAJOR changes the second number is for minor changes and the third number is for small changes
> **Command:** pyinstaller --onefile --noconsole --name "ULMCSVTOOLV1.3.0" --icon "ULM_icon.ico" --add-data "templateFile.csv;." backend.py
