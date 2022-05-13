# -*- coding: utf-8 -*-

"""
Nickolay Nonard <kelciour@gmail.com>
"""

import json
import requests
import time
import io
import os
import re
import subprocess
import urllib.parse
import sys
import threading

from bs4 import BeautifulSoup

from aqt.qt import *
from aqt.utils import showInfo, tooltip
from anki.hooks import addHook, runHook
from anki.lang import ngettext
from anki.utils import checksum, tmpfile, noBundledLibs

from anki.sound import _packagedCmd, si
from distutils.spawn import find_executable

from .designer.main import Ui_Dialog

# New Libraries
from aqt.progress import ProgressManager
from aqt.taskman import TaskManager
from aqt import gui_hooks


# https://github.com/glutanimate/html-cleaner/blob/master/html_cleaner/main.py#L59
sys.path.append(os.path.join(os.path.dirname(__file__), "vendor"))

import concurrent.futures

import warnings
# https://github.com/python-pillow/Pillow/issues/3352#issuecomment-425733696
warnings.filterwarnings("ignore", "(Possibly )?corrupt EXIF data", UserWarning)


headers = {
  "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.67 Safari/537.36"
}

# Update Note Field after Image Scraping
def updateField(mw, config, nid, fld, images, overwrite):
    if not images: # if no images, exit and return nothing
        return

    imgs = [] # image fnames for insertion to note
    for fname, data in images: # for list of (fname,data) tuples, add fnames to 'imgs' list of filenames
        fname = mw.col.media.writeData(fname, data)
        filename = '<img src="%s">' % fname
        imgs.append(filename)

    note = mw.col.getNote(nid)
    delimiter = config.get("Delimiter", " ")
    
    if overwrite == "Append":
        if note[fld]:
            note[fld] += delimiter
        note[fld] += delimiter.join(imgs)
    else:
        note[fld] = delimiter.join(imgs)
    # END IF

    note.flush()
# END FUNCTION

# Scrape Images from URL
def scrapeImages(nid, fld, html, img_width, img_height, img_count, fld_overwrite):
    from PIL import Image, ImageSequence, UnidentifiedImageError

    # Extract image divs from html
    soup = BeautifulSoup(html, "html.parser")
    rg_meta = soup.find_all("div", {"class": "rg_meta"}) # collect all div.rg_meta elements from html
    metadata = [json.loads(e.text) for e in rg_meta] # for each div in rg_meta, convert json to dict, add to list
    results = [d["ou"] for d in metadata] # take img tags? from list of json, add to results list

    if not results: # if results empty ...
        regex = re.escape("AF_initDataCallback({") # escape special chars in string
        regex += r'[^<]*?data:[^<]*?' + r'(\[[^<]+\])' # search for string w/ 'data:'

        for txt in re.findall(regex, html): # for each result string from re.findall ...
            data = json.loads(txt) # convert json from result to dict

            try:
                for d in data[31][0][12][2]:
                    try:
                        results.append(d[1][3][0]) # add URLs to results list
                    except Exception as e:
                        pass
            except Exception as e:
                pass
        # END FOR
    # END IF

    cnt = 0
    images = []
    for url in results: # for each url in results list
        try:
            r = requests.get(url, headers=headers, timeout=15) #HTTP GET Request, 'r'
            r.raise_for_status()
            data = r.content # image file?

            # Skip if doc header is text or svg
            if 'text/html' in r.headers.get('content-type', ''):
                continue
            # END IF
            if 'image/svg+xml' in r.headers.get('content-type', ''):
                continue
            # END IF

            url = re.sub(r"\?.*?$", "", url) # get text after '?' in request url for filename
            path = urllib.parse.unquote(url) # parse url
            fname = os.path.basename(path) # set filename

            if not fname:
                fname = checksum(data)
            # END IF
            
            # == IMAGE PROCESSING ==
            im = Image.open(io.BytesIO(data)) # stream image data and open

            if img_width > 0 or img_height > 0:
                width, height = im.width, im.height

                if img_width > 0:
                    width = min(width, img_width) # calc img width from min of query width or actual width
                # END IF

                if img_height > 0:
                    height = min(height, img_height) # ditto for height
                # END IF

                buf = io.BytesIO()

                if getattr(im, 'n_frames', 1) == 1: # detect static img or gif by frame count
                    im.thumbnail((width, height)) # set image dims
                    im.save(buf, format=im.format, optimize=True) # save img

                # Gif handling?
                elif mpv_executable: # if gif
                    thread_id = threading.get_native_id()
                    tmp_path = tmpfile(suffix='.{}'.format(thread_id))
                    with open(tmp_path, 'wb') as f:
                        f.write(data)

                    img_fmt = im.format.lower()
                    img_ext = '.' + img_fmt
                    img_path = tmpfile(suffix=img_ext)
                    cmd = [mpv_executable, tmp_path, "-vf", "lavfi=[scale='min({},iw)':'min({},ih)':force_original_aspect_ratio=decrease:flags=lanczos]".format(img_width, img_height), "-o", img_path]

                    with noBundledLibs():
                        p = subprocess.Popen(cmd, startupinfo=si, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env=env)
                    # END WITH

                    if p.wait() == 0:
                        with open(img_path, 'rb') as f:
                            buf.write(f.read())
                    # END IF
                else:
                    buf = io.BytesIO(data)
                # END IF

                data = buf.getvalue() # set data to bytes
            # END IF

            images.append((fname, data)) # add image data to images list as tuple
            cnt += 1

            if cnt == img_count:
                break
            # END IF
        # END TRY

        # Error Handling
        except requests.packages.urllib3.exceptions.LocationParseError: # fix from anonymous @ https://ankiweb.net/shared/info/561924305
            pass
        except requests.exceptions.RequestException:
            pass
        except UnidentifiedImageError:
            pass
        except UnicodeError as e:
            # UnicodeError: encoding with 'idna' codec failed (UnicodeError: label empty or too long)
            # https://bugs.python.org/issue32958
            if str(e) != "encoding with 'idna' codec failed (UnicodeError: label empty or too long)":
                raise
            # END IF
        # END EXCEPT

    # END FOR
    
    return (nid, fld, images, fld_overwrite)
# END FUNCTION

# Run query, add images to notes
def updateNotes(browser, mw, nids, sf, sq, config):
    browser.model.beginReset()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        jobs = []
        processed = set()

        # For each Note ID in list of Note IDs ...
        for c, nid in enumerate(nids, 1): 
            note = mw.col.getNote(nid)

            w = note[sf] #source field content

            for q in sq: # for each query from form ...
                df = q["Field"] # destination field, e.g. {{img}}

                # Skip conditions
                if not df:      # if destination form field empty, skip to next note ID
                    continue
                if note[df] and q["Overwrite"] == "Skip":   # if skip selected, go to next note ID
                    continue
                
                # == GENERAL FORMATTING OF SOURCE FIELD TEXT ==
                # Strip HTML from note source field
                w = re.sub(r'</?(b|i|u|strong|span)(?: [^>]+)>', '', w) # remove basic Anki formatting
                w = re.sub(r'\[sound:.*?\]', '', w)
                if '<' in w: # if left element bracket, '<', still in field text... why?
                    soup = BeautifulSoup(w, "html.parser")
                    for s in soup.stripped_strings: # extract strings from html and strip whitespace
                        w = s
                        break # take only first string from source field...why?
                else:
                    w = re.sub(r'<br ?/?>[\s\S]+$', ' ', w)
                    w = re.sub(r'<[^>]+>', '', w)
                # END IF

                # Remove and Reformat Clozes
                clozes = re.findall(r'{{c\d+::(.*?)(?::.*?)?}}', w)
                if clozes:
                    w = ' '.join(clozes)
                # END IF

                # == CREATE & EXECUTE GET REQ ==
                query = q["URL"].replace("{}", w) # insert field text into query form field text

                # Add requests and scrape to queue list
                try:
                    r = requests.get("https://www.google.com/search?tbm=isch&q={}&safe=active".format(query), headers=headers, timeout=15) # replace '{}' with formatted query, perform GET request
                    r.raise_for_status() # raise error if request failure
                    html = r.text

                    future = executor.submit(scrapeImages, nid, df, html, q["Width"], q["Height"], q["Count"], q["Overwrite"]) # async execution of 'getImages'
                    jobs.append(future) # add to list of jobs

                except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
                    pass
            # END FOR

            done, not_done = concurrent.futures.wait(jobs, timeout=0) # wait for jobs' completion, then add list of outputs to list
            for future in done: # loop through currently completed jobs, add to 'done' list, remove from 'jobs'
                nid, fld, images, overwrite = future.result()
                updateField(mw, config, nid, fld, images, overwrite)
                
                # Status Bar
                processed.add(nid)
                jobs.remove(future)
            else: # triggers at end of loop if no "break"
                label = 'Processing ' + str(len(processed)) + ' of ' + str(len(nids))
                mw.taskman.run_on_main(lambda:mw.progress.update(label=label,value=len(processed),max=len(nids)))
        # END FOR

        for future in concurrent.futures.as_completed(jobs): # run loop as jobs complete
            nid, fld, images, overwrite = future.result() # images is tuple of (fname,data)
            updateField(mw, config, nid, fld, images, overwrite)
            
            # Status Bar
            processed.add(nid)
            label = 'Processing ' + str(len(processed)) + ' of ' + str(len(nids))
            mw.taskman.run_on_main(lambda:mw.progress.update(label=label,value=len(processed),max=len(nids)))
        # END FOR

    browser.model.endReset()
    mw.requireReset()
# END FUNCTION

# Query Form UI
def updateNotesUI(browser, nids):
    # unused: from PIL import Image, ImageSequence, UnidentifiedImageError

    mw = browser.mw

    d = QDialog(browser)
    frm = Ui_Dialog()
    frm.setupUi(d)

    icon = os.path.join(os.path.dirname(__file__), "icons", "google.ico")
    d.setWindowIcon(QIcon(icon))

    config = mw.addonManager.getConfig(__name__)

    mpv_executable, env = find_executable("mpv"), os.environ
    if mpv_executable is None:
        mpv_path, env = _packagedCmd(["mpv"])
        mpv_executable = mpv_path[0]
        try:
            with noBundledLibs():
                p = subprocess.Popen([mpv_executable, "--version"], startupinfo=si)
        except OSError:
            mpv_executable = None

    note = mw.col.getNote(nids[0])
    fields = note.keys()

    # Form Setup
    frm.srcField.addItems(fields)
    fld = config["Source Field"]
    if fld in fields:
        frm.srcField.setCurrentIndex(fields.index(fld))

    for i, sq in enumerate(config["Search Queries"], 1):
        name = sq["Name"]
        url = sq["URL"]
        fld = sq["Field"]
        cnt = sq.get("Count", 1)
        width = sq.get("Width", -1)
        height = sq.get("Height", 260)
        overwrite = sq.get("Overwrite", "Skip")

        # backward compatibility with the previous version
        if overwrite == True:
            overwrite = "Overwrite"
        elif overwrite == False:
            overwrite = "Skip"

        lineEdit = QLineEdit(name)
        frm.gridLayout.addWidget(lineEdit, i, 0)

        lineEdit = QLineEdit(url)
        frm.gridLayout.addWidget(lineEdit, i, 1)

        combobox = QComboBox()
        combobox.setObjectName("targetField")
        combobox.addItem("<ignored>")
        combobox.addItems(fields)
        if fld in fields:
            combobox.setCurrentIndex(fields.index(fld) + 1)
        frm.gridLayout.addWidget(combobox, i, 2)

        spinBox = QSpinBox()
        spinBox.setMinimum(1)
        spinBox.setValue(cnt)
        spinBox.setStyleSheet("""
           QSpinBox {
            width: 24;
        }""")
        frm.gridLayout.addWidget(spinBox, i, 3)

        checkBox = QComboBox()
        checkBox.setObjectName("checkBox")
        checkBox.addItem("Skip")
        checkBox.addItem("Overwrite")
        checkBox.addItem("Append")
        checkBox.setCurrentIndex(checkBox.findText(overwrite))
        frm.gridLayout.addWidget(checkBox, i, 4)

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Width:"))
        spinBox = QSpinBox()
        spinBox.setMinimum(-1)
        spinBox.setMaximum(9999)
        spinBox.setValue(width)
        spinBox.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        hbox.addWidget(spinBox)
        frm.gridLayout.addLayout(hbox, i, 5)

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Height:"))
        spinBox = QSpinBox()
        spinBox.setMinimum(-1)
        spinBox.setMaximum(9999)
        spinBox.setValue(height)
        spinBox.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        hbox.addWidget(spinBox)
        frm.gridLayout.addLayout(hbox, i, 6)

    frm.gridLayout.setColumnStretch(1, 1)
    frm.gridLayout.setColumnMinimumWidth(1, 120)

    columns = ["Name:", "Search Query:", "Target Field:", "Count:", "If not empty?", '', '']
    for i, title in enumerate(columns):
        frm.gridLayout.addWidget(QLabel(title), 0, i)

    if not d.exec_():
        return

    sf = frm.srcField.currentText()
    # End Form setup

    # Query Setup
    # Add Each form line to sq (Search Queries) array
    sq = []
    columns = ["Name", "URL", "Field", "Count", 'Overwrite', 'Width', 'Height']

    # For each cell in form...
    for i in range(1, frm.gridLayout.rowCount()): 
        q = {}  # query field contents
        for j in range(frm.gridLayout.columnCount()):
            key = columns[j]
            if not key:
                continue
            item = frm.gridLayout.itemAtPosition(i, j)

            if isinstance(item, QWidgetItem):
                item = item.widget()
            elif isinstance(item, QLayoutItem):
                item = item.itemAt(1).widget()

            if isinstance(item, QComboBox) and item.objectName() == "targetField":
                q[key] = item.currentText()
                if q[key] == "<ignored>":
                    q[key] = ""
            elif isinstance(item, QSpinBox):
                q[key] = item.value()
            elif isinstance(item, QComboBox) and item.objectName() == "checkBox":
                q[key] = item.currentText()
            else:
                q[key] = item.text()
        sq.append(q)

    # Write current values to config
    config["Source Field"] = sf
    config["Search Queries"] = sq #add search queries to config
    mw.addonManager.writeConfig(__name__, config)
    
    # Query execution
    mw.checkpoint("Add Google Images") # Wait for button press
    
    mw.taskman.with_progress(
        label='Processing...!',
        immediate=True, 
        task=lambda: updateNotes(browser, mw, nids, sf, sq, config),
        on_done=lambda dummy: showInfo('Complete!',parent=browser)
    )

def onAddImages(browser):
    nids = browser.selectedNotes()
    if not nids:
        tooltip("No cards selected.")
        return
    updateNotesUI(browser, nids)
    # browser.mw.taskman.with_progress(label='Processing...!',immediate=True, task=lambda: updateNotes(browser, nids),on_done=lambda: showInfo('Processed.', parent=browser))

def setupMenu(browser):
    menu = browser.form.menuEdit
    menu.addSeparator()
    a = menu.addAction('Add Google Images')
    a.triggered.connect(lambda _, b=browser: onAddImages(b))


addHook("browser.setupMenus", setupMenu)
#gui_hooks.browser_will_show_context_menu(onAddImages)