import pandas as pd

# 1. Load your original headers-free file
df = pd.read_csv('example_carbon_data without headers.csv', header=None)

# 2. Build 30-minute timestamp increments starting at Day 100, 2023 at 08:00
start_dt = pd.to_datetime('2023-01-01') + pd.Timedelta(days=99) + pd.Timedelta(hours=8)
timestamps = [start_dt + pd.Timedelta(minutes=30*i) for i in range(len(df))]

# 3. Replace Year (Col 0), Day of Year (Col 1), and Time (Col 2)
df[0] = [ts.year for ts in timestamps]
df[1] = [ts.dayofyear for ts in timestamps]
df[2] = [int(ts.strftime('%H%M')) for ts in timestamps]

# 4. Save to your local folder
df.to_csv('example_carbon_data_2023_modified.csv', index=False, header=False)
print("Saved 1,827 rows successfully!")
