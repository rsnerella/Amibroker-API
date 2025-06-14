import pandas as pd
import asyncio
import aiohttp
import json
from datetime import datetime, timezone, timedelta
import nest_asyncio
import csv
import os
import win32com.client
import sys
import ssl
import certifi


#Inputs
login_file = r'R:\FlattradeLogin1.txt'
output_dir = r'C:\HistoricalData'
base_url = 'https://piconnect.flattrade.in/PiConnectTP/'
historical_ep = 'TPSeries'


#start_date = datetime.today().strftime('%d-%m-%Y')
#end_date = datetime.today().strftime('%d-%m-%Y')
#start_date = '02-05-2025'
#end_date = '02-05-2025'
#do_import = 'No'
#do_delete = 'Yes'
#master_file = 'ScripMaster'

start_date = sys.argv[1]
end_date = sys.argv[2]
do_import = sys.argv[3]
do_delete = sys.argv[4]
master_file = sys.argv[5]
master_list = fr'C:\API\{master_file}.csv'

def read_csv_dict(file_path):
    data_dict = {}
    with open(file_path, mode='r') as file:
        reader = csv.reader(file)
        for row in reader:
            key, value = row
            data_dict[key] = value
    return data_dict


# PC Timw now
def pc_time():
    return datetime.now().strftime('%d-%m-%Y %H:%M:%S')

#Timestamp to IST
def epoch_to_ist(unix_timestamp):
    utc_time = datetime.fromtimestamp(int(unix_timestamp), tz=timezone.utc)
    ist_time = utc_time.astimezone(timezone(timedelta(hours=5, minutes=30)))
    return ist_time.strftime('%d-%m-%Y %H:%M:%S')

#Date,Time to UnixTime Stamp
def epoch(date, time):
    dt = datetime.strptime(f"{date} {time}", '%d-%m-%Y %H:%M:%S')
    return int(dt.timestamp())



async def hist_data_single(session, base_url, end_point, user_id, jkey, symbol, exchange, token, startdate, enddate, output_dir, retries=3, delay=2, do_import='Yes', do_delete='Yes'):
    url = f"{base_url}{end_point}"
    jdata = {
        "uid": user_id,
        "exch": exchange,
        "token": token,
        "st": str(startdate),
        "et": str(enddate),
        "intrv": '1'
    }
    payload = f'jData={json.dumps(jdata)}&jKey={jkey}'

    ssl_context = ssl.create_default_context(cafile=certifi.where())

    for attempt in range(retries):
        try:
            async with session.post(url, data=payload, ssl=ssl_context) as response:
                if response.status == 200:
                    data = await response.json()

                    if isinstance(data, str):
                        print(f"Error: Data for {symbol} returned as a string, no retry needed.")
                        return

                    rows = []
                    for record in data:
                        if record.get("stat") == "Ok":
                            ist_time = epoch_to_ist(record['ssboe'])
                            date, time = ist_time.split(' ')

                            rows.append([
                                symbol, date, time,
                                record['into'],  # Open
                                record['inth'],  # High
                                record['intl'],  # Low
                                record['intc'],  # Close
                                record['intv'],  # Volume
                                record['oi']     # OI
                            ])

                    df = pd.DataFrame(rows, columns=['Symbol', 'Date', 'Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'OI'])
                    output_file = f"{output_dir}/{symbol}.csv"
                    df.to_csv(output_file, index=False)

                    if do_import == 'Yes':
                        
                        AB = win32com.client.Dispatch("Broker.Application")
                        AB.Import(0, output_file, "OneMinuteFeed.format")
                        # AB.RefreshAll()

                        if do_delete == 'Yes':
                            try:
                                os.remove(output_file)
                            except Exception as e:
                                print(f"Warning: Could not delete {output_file} - {str(e)}")
                    return

                else:
                    print(f"Error: Failed to fetch data for {symbol} {token}, status code {response.status}")

        except aiohttp.ClientError as e:
            print(f"Attempt {attempt + 1}: Client error for {symbol} {token}, status code {response.status}: {str(e)}")
        except AttributeError as e:
            if "'str' object has no attribute 'get'" in str(e):
                print(f"Error: Data processing failed for {symbol}: {str(e)}. No retry.")
                return
            else:
                print(f"Attempt {attempt + 1}: Attribute error for {symbol}: {str(e)}")
        except Exception as e:
            print(f"Attempt {attempt + 1}: Exception for {symbol} {token}, status code {response.status}: {str(e)}")

        if attempt < retries - 1:
            await asyncio.sleep(delay)
        else:
            print(f"Max retries reached for {symbol}. Giving up.")



async def hist_data_list(base_url, end_point, user_id, jkey, master_list, startdate, enddate, output_dir, batch_size=10, do_import='Yes', do_delete='Yes'):
    async with aiohttp.ClientSession() as session:
        df_master = pd.read_csv(master_list, names=["Exchange", "Symbol", "Token"])
        df_master = df_master[df_master['Exchange'] != 'Exchange']  # Filter out header row

        for i in range(0, len(df_master), batch_size):
            tasks = []
            batch = df_master.iloc[i:i + batch_size]

            for _, row in batch.iterrows():
                task = hist_data_single(
                    session, base_url, end_point, user_id, jkey,
                    row['Symbol'], row['Exchange'], row['Token'],
                    startdate, enddate, output_dir,
                    do_import=do_import, do_delete=do_delete
                )
                tasks.append(task)

            await asyncio.gather(*tasks)





#Execute
startdate = epoch(start_date, '00:00:00')
enddate = epoch(end_date, '23:59:59')

            
login_dict = read_csv_dict(login_file)
user_id = login_dict['user']
jkey = login_dict['token']
print(f"User ID: {user_id}")
print(f"JKey: {jkey}")

print(pc_time())
print(start_date , "-", end_date)
asyncio.run(hist_data_list(base_url, historical_ep, user_id, jkey, master_list, startdate, enddate, output_dir, batch_size=25, do_import=do_import, do_delete=do_delete))
print(pc_time())
input("Press Enter to exit...")
