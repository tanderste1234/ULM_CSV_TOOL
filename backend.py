import csv
CHUNK_SIZE = 50_000


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


filterByDate("test.csv", "outputdatefiltered.csv",
             "date", "06/14/2026", "09/15/2025")

filterByHeader("test.csv", "filterbycolname.csv", ["fname", "lname", "date"])
