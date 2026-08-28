import csv
CHUNK_SIZE = 50_000
import os

def filterByHeader(filename, outputfilename, arrayOfTargetColnames):
    with open(filename, "r", encoding="utf-8") as f:
        # Creates the stream reader and removes all whitespace
        reader = csv.reader(f, skipinitialspace=True)
        header = next(reader)  # Grab the header row
        targetIndexes = []  # initializing the indexes we want
        targetHeaders = []  # this is ordered list of our headers
        chunk = []  # initializing the chunk so that anything left over in the chunk can be written
        # this loops through the header and keeps track of the index and columname
        for index, colname in enumerate(header):
            # if we found what we are interested in we add the index to our list of stuff we want
            if colname in arrayOfTargetColnames:
                targetIndexes.append(index)
                targetHeaders.append(colname)
        # this opens our output file with a buffer
        with open(outputfilename, "w", newline="", encoding="utf-8", buffering=2 * 1024 * 1024) as f:
            writer = csv.writer(f)  # create write stream
            # writes the column names we're interested in
            writer.writerow(targetHeaders)
            for row in reader:  # this loops through the rows in the file being filtered
                newRow = []
                # this finds all the values we're looking for one by one and creates the new row to be writen
                for index, value in enumerate(row):
                    if index in targetIndexes:
                        newRow.append(value)
                chunk.append(newRow)  # this is just to keep the I/O ops down
                if len(chunk) >= CHUNK_SIZE:  # this is where we actually write everything
                    writer.writerows(chunk)
                    chunk.clear()
            if len(chunk) > 0:
                writer.writerows(chunk)
                chunk.clear()


def filterByDate(filename, outputfilename, dateColName, *args):
    with open(filename, "r", encoding="utf-8") as f:
        # Creates the stream reader and removes all whitespace
        reader = csv.reader(f, skipinitialspace=True)
        header = next(reader)  # Grab the header row
        targetIndexes = []  # initializing the indexes we want
        chunk = []  # initializing the chunk so that anything left over in the chunk can be written
        # this loops through the header and keeps track of the index and columname
        for index, colname in enumerate(header):
            if colname == dateColName:  # if we found what we are interested in we add the index to our list of stuff we want
                targetIndexes.append(index)
        # this opens our output file with a buffer
        with open(outputfilename, "w", newline="", encoding="utf-8", buffering=2 * 1024 * 1024) as f:
            writer = csv.writer(f)  # create write stream
            writer.writerow(header)
            for row in reader:  # this loops through the rows in the file being filtered
                # this finds all the values we're looking for one by one and creates the new row to be writen
                for index, value in enumerate(row):
                    if index in targetIndexes:
                        if value in args:  # uses the same format as the data file
                            chunk.append(row)
                if len(chunk) >= CHUNK_SIZE:  # this is where we actually write everything
                    writer.writerows(chunk)
                    chunk.clear()
            if len(chunk) > 0:
                writer.writerows(chunk)
                chunk.clear()


filterByHeader("random_dataset_4000x30.csv", "temp.csv", ["Date","Revenue","Expenses","Profit", "Margin_Pct","Unit_Price","Units_Sold", "Customer_Visits"])

filterByDate("temp.csv", "filtered4000X8.csv", "Date", "2023-01-02","2023-01-03","2023-01-04","2023-01-05","2023-01-06","2023-01-07","2023-01-08","2023-01-09","2023-01-10")
os.remove("temp.csv")
filterByHeader("dataset_25k.csv", "temp.csv", ["date","field_1","field_1","field_2", "field_3","field_4","field_5", "field_6"])
filterByDate("temp.csv", "filtered25Kx6.csv", "date", "2021-01-02","2021-01-03","2021-01-04","2021-01-05","2021-01-06","2021-01-07","2021-01-08","2021-01-09","2021-01-10")
os.remove("temp.csv")
filterByHeader("large_dataset_60k.csv", "temp.csv", ["date","field_1","field_1","field_2", "field_3","field_4","field_5", "field_6"])
filterByDate("temp.csv", "filtered60Kx6.csv", "date", "2020-01-02","2020-01-03","2020-01-04","2020-01-05","2020-01-06","2020-01-07","2020-01-08","2020-01-09","2020-01-10")
os.remove("temp.csv")
filterByHeader("large_dataset_60k.csv", "temp.csv", ["date","field_5","field_1","field_8", "field_29","field_4","field_11"])
filterByDate("temp.csv", "filtered60Kx5.csv", "date", "2021-01-02","2021-01-03","2021-01-04","2021-01-05","2021-01-06","2021-01-07","2021-01-08","2021-01-09","2021-01-10")
os.remove("temp.csv")
