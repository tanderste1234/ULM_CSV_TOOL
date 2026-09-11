# ULM_CSV_TOOL
the replacement for the old query system for ULM
## 🛠️ Prerequisites & Setup


Follow these steps to install and run the tool.
### 1. Download template file
1. Open the `template.csv` file in this repository by clicking on the file name.
2.  On the file preview screen, locate the group of 3 buttons in the top-right corner (the first button is labeled **Raw**).
3. Click the 3rd button on the right (the download icon, which shows the tooltip **"Download raw file"** when you hover over it) to save the file to your computer.
4. when the save window opens up save it somewhere you can easily access as you will need to know where it is when using the tool

### 2. Downloading The Exe File

1. Open the `releases` folder in this repository.
2. Click on the `ULMCSVTOOLV1.2.3.exe` file.
3. On the file preview screen, locate the group of 3 buttons in the top-right corner (the first button is labeled **Raw**).
4. Click the 3rd button on the right (the download icon, which shows the tooltip **"Download raw file"** when you hover over it) to save the file to your computer.
5. you should save the tool somewhere easy to get to as you will need to either make a shortcut or have this file on the desktop

> **Note:** `ULMCSVTOOLV1.2.3.exe` is a fully self-contained file. You do not need to install Python, run any command-line scripts, or download additional setup files—just open the file, and you are good to go!
## 💻 Using The Tool
1. first you will need to double-click the `ULMCSVTOOLV1.2.3.exe` file to run the tool
2. next you will need to hit the <kbd>Browse...</kbd> button in the program window next to the `input file:` label and then use window's file explorer to find where you put the `template.csv` file and select it
3. once you select it the program will automatically populate the headers
4. after doing that you will need to click the checkbox labeled "CSV has no header row(manually define below)" so that is is checked ✅
5. then you will go back up to the input file and hit the <kbd>Browse...</kbd> button again and navigate to your data file's location using windows file explorer and select the file
> **Note:** the output file will automatically name itself after your input file's name with `_processed.csv` on the end of the original file name if you do not want the output file to be named this way please click the <kbd>Browse...</kbd> button on the end of the input labeled output file and navigate to the place you would like to have your output file then name it whatever you want
7. once you have either left the automatically named file or you named it your self you then need to select what fields you are interested in and enter them in a comma separated list in the columns to keep field
> **Note:** the time field is not automatically kept so if you would like the times kept please remember to add it in this field
9. once you have decided what fields you are interested in and entered them correctly
10. in the next two fields labeled Year Column and Date Column refer to the headers first two entries and enter the names with out commas or spaces this may change but "year" should be the Year Column input and "day" should be entered into the Date Column input
11. the next input is your date format field choose which ever format you want the default is YYYY-MM
12. once you select the date format of your preference then please enter a comma separated list of start dates and then a respective list of end dates **Note:** Please make sure to enter an equal amount of start and end dates as the code will not work other wise and also make sure to follow the date format you have selected as improperly formatted dates will not yield correct results  also please make sure use dates that are valid for your data as it will not show anything not in the data file
13. once you have correctly entered the dates hit the <kbd>Start Processing</kbd> button on the bottom left of the window next to the <kbd>Show Debug Window</kbd> button. **Note:** the Show debug window button is only for finding problems with the application and you should not need it
14. after the processing is finished there should be a pop up saying the processing completed successfully click the <kbd>okay</kbd> button
15. now open the output file with whatever program you wish and check that your filtered data is there
> **Note:** if you kept the default it will have made the output in the input file folder with `_processed.csv` on the end of it
