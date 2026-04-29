
import requests as re
from bs4 import BeautifulSoup as bs
from datetime import datetime as dt
import schedule, time, os, sys, json
from config import *
from tkinter import *
from tkinter import scrolledtext
import threading

# pyinstaller cmd> pyinstaller.exe --onefile --add-data "hsvr_100g.ico;." --icon=hsvr_100g.ico -w .\gui_hserver.py

BOT_NAME = 'Hibor Bot'
conf_file = 'hserver.cfg'

class sysRedirector:
    def __init__(self, text_widget, tag='stdout'):
        self.text_widget = text_widget
        self.tag = tag
    def write(self, string):
        self.text_widget.insert(END, string, self.tag)        
        self.text_widget.see(END)  # Auto-scroll to the end
    def flush(self):
        pass # Needed for some environments

def get_hibor():
    response = re.get(hibor_url)
    soup = bs(response.text, 'html.parser')

    # Check if today is a working day
    tags = soup.body.find_all(string='This is a non-working day. Please select another day.')
    if len(tags) > 0:
        outputTxt(f"[{dt.now().strftime(dt_format)}] Today is a non-working weekday!")
        return {}

    rates = {}
    m_tags = soup.find_all('div', class_='general_table_cell hibor_maturity')
    r_tags = soup.find_all('div', class_='general_table_cell last')
    for m, r in zip(m_tags[1:], r_tags[1:]):  # skip header row
        rates[m.text.strip()] = float(r.text.strip())
    outputTxt(f"[{dt.now().strftime(dt_format)}] Hibor rates: {rates}")
    return rates

def load_conf(c_file=conf_file, writeFile=False):
    global update_time,ac_thres_hi,ac_thres_lo, ic_thres_hi, ic_thres_lo
    if (os.path.exists(c_file) and writeFile==False):
        file_data = json.load(open(c_file))
        update_time = file_data['update_time']
        ac_thres_lo = file_data['ac_thres_lo']
        ac_thres_hi = file_data['ac_thres_hi']
        ic_thres_lo = file_data['ic_thres_lo']
        ic_thres_hi = file_data['ic_thres_hi']
    else:
        file_data = {'update_time':update_time, 
                     'ac_thres_lo':ac_thres_lo, 
                     'ac_thres_hi':ac_thres_hi, 
                     'ic_thres_lo':ic_thres_lo, 
                     'ic_thres_hi':ic_thres_hi}
        json.dump(file_data, open(conf_file,'w'))   
    return file_data


def tg_alert(mth_hibor, key, chat_id, thres_hi, thres_lo=0, rates={}):
    if mth_hibor > thres_hi or mth_hibor < thres_lo:
        alert = f'{alert_sym}OUT OF RANGE: {thres_lo} to {thres_hi}{alert_sym}'
    else:
        alert = f'{tick_sym}Within Range: {thres_lo} to {thres_hi}{tick_sym}'

    if rates:
        today = dt.now().strftime('%Y-%m-%d')
        text = f'HIBOR Rates {today}\n' + '\n'.join(f'{k}: {v}' for k, v in rates.items()) + '\n\n' + alert
        if rates.get('Overnight', 0) > rates.get('1 Month', 0):
            text += f"\n{alert_sym}ALERT: Overnight ({rates['Overnight']}) > 1 Month ({rates['1 Month']}){alert_sym}"
        else:
            text += f"\n{tick_sym}Overnight ({rates['Overnight']}) < 1 Month ({rates['1 Month']}){tick_sym}"
    else:
        text = '1-Mth Hibor is '+str(mth_hibor) + '\n' + alert if mth_hibor > 0 else 'Hibor is not available today'
    send_url = f'https://api.telegram.org/bot{key}/sendMessage?chat_id={chat_id}&parse_mode=NONE&text={text}'
    try:
        response = re.get(send_url)
        return response.json()
    except Exception as e:
        error={'ok': 0, 'description': f"tg_send error: {e}!!"}
        return error

def is_weekday():
    # Check if today is a weekday (Monday to Friday)
    return dt.now().weekday() < 5

def hibor_check():
    if is_weekday():
    # Only run the check if today is a weekday
        try:
            rates = get_hibor()
            mth_hibor = rates.get('1 Month', 0.0)
        except Exception as e:
            outputTxt(f"Connection error, skipping this check: {e}")
            return
        if not rates:
            return
        # TG alert for Adrian
        ack=tg_alert(mth_hibor, AC_TG_KEY, AC_TG_CHATID, ac_thres_hi, ac_thres_lo, rates)
        if ack['ok']:
            outputTxt(f"[{dt.now().strftime(dt_format)}] Alert to Adrian: msg_id=[{ack['result']['message_id']}]")
        else:
            outputTxt(f"[{dt.now().strftime(dt_format)}] Alert error to Adrian: {ack['description']}")

        # TG alert for Isaac
        ack=tg_alert(mth_hibor, AC_TG_KEY, IC_TG_CHATID, ic_thres_hi, ic_thres_lo, rates)
        if ack['ok']:
            outputTxt(f"[{dt.now().strftime(dt_format)}] Alert to Isaac: msg_id=[{ack['result']['message_id']}]")
        else:
            outputTxt(f"[{dt.now().strftime(dt_format)}] Alert error to Isaac: {ack['description']}")

    else:
        outputTxt(f"[{dt.now().strftime(dt_format)}] Take a break, it's weekend!")




running = False
thread_on = True
# inputtime=update_time

def clickStart():
    global update_time, running
    update_time = eTime.get()
    load_conf(writeFile=True)
    running=True
    eTime['state'] = DISABLED
    bStart['state'] = DISABLED
    bStop['state'] = NORMAL
    server_thread = threading.Thread(target=startSvr)
    server_thread.start()

def clickStop():
    global running
    running=False
    eTime['state'] = NORMAL
    bStart['state'] = NORMAL
    bStop['state'] = DISABLED

def clickUpdate():
    global ac_thres_lo,ac_thres_hi,ic_thres_lo,ic_thres_hi
    ac_thres_lo = float(ac_lo.get())
    ac_thres_hi = float(ac_hi.get())
    ic_thres_lo = float(ic_lo.get())
    ic_thres_hi = float(ic_hi.get())
    load_conf(writeFile=True)

def outputTxt(txt):
    text_area.insert(END,f'{txt}\n')
    text_area.yview(END)

def startSvr():
    outputTxt(f"[{dt.now().strftime(dt_format)}] Hibor Server [V1.2] Started [report {update_time} DAILY]...............")
    
    job = schedule.every().day.at(update_time).do(hibor_check)
    # job = schedule.every(5).seconds.do(hibor_check)
    while running:
        schedule.run_pending()
        time.sleep(1)
    schedule.cancel_job(job)
    if gui_on: outputTxt(f"[{dt.now().strftime(dt_format)}] Hibor Server [V1.2] Stopped!!")
    
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

#GUI
load_conf()
root=Tk()
root.title("Hibor TG Server V1.1")
icon_path = resource_path('hsvr_100g.ico')
root.iconbitmap(icon_path)
root.geometry("800x400")

input_frame = Frame(root)
input_frame.pack(expand=True, fill='both')

alert_label = Label(input_frame,text='Alert Time:')
alert_label.pack(side='left', padx=10, pady=10)

eTime = Entry(input_frame, width=20, font=('Helvetica', 10))
eTime.insert(END, f'{update_time}')
eTime.pack(side='left', padx=10, pady=10)

bStart = Button(input_frame, text="Start Server", command=clickStart)
bStart.pack(side='left', padx=10, pady=10)

bStop = Button(input_frame, text="Stop Server", command=clickStop)
bStop['state'] = DISABLED
bStop.pack(side='left', padx=10, pady=10)

bNow = Button(input_frame, text="Report NOW!", command=hibor_check)
bNow.pack(side='left', padx=20, pady=10)

thres_frame = Frame(root)
thres_frame.pack(expand=True, fill='both')
ac_label = Label(thres_frame,text='AC Thresholds (Lo-Hi):')
ac_label.pack(side='left', padx=5, pady=10)
ac_lo = Entry(thres_frame, width=5, font=('Helvetica', 10))
ac_lo.insert(END, f'{ac_thres_lo}')
ac_lo.pack(side='left', padx=5, pady=10)
ac_hi = Entry(thres_frame, width=5, font=('Helvetica', 10))
ac_hi.insert(END, f'{ac_thres_hi}')
ac_hi.pack(side='left', padx=5, pady=10)

ic_label = Label(thres_frame,text='IC Thresholds (Lo-Hi):')
ic_label.pack(side='left', padx=5, pady=10)
ic_lo = Entry(thres_frame, width=5, font=('Helvetica', 10))
ic_lo.insert(END, f'{ic_thres_lo}')
ic_lo.pack(side='left', padx=5, pady=10)
ic_hi = Entry(thres_frame, width=5, font=('Helvetica', 10))
ic_hi.insert(END, f'{ic_thres_hi}')
ic_hi.pack(side='left', padx=5, pady=10)

bUpdate = Button(thres_frame, text="Update Thresholds", command=clickUpdate)
bUpdate.pack(side='left', padx=10, pady=10)

text_area = scrolledtext.ScrolledText(root)
text_area.config(background='#222222', foreground="#FFEE00")
text_area.pack(expand=True, fill='both')

text_area.tag_config('stderr', foreground="#FCB0B0")
text_area.tag_config('stdout', foreground="#6FE9FF")
text_area.pack(expand=True, fill='both')
# Redirect stdout and stderr to the text area
sys.stdout = sysRedirector(text_area, tag='stdout')
sys.stderr = sysRedirector(text_area, tag='stderr')

gui_on=True
clickStart()
root.mainloop()
gui_on=False
running=False