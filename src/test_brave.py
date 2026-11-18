from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

options = Options()
options.binary_location = BRAVE_PATH
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)
driver.get("https://www.google.com")
print("Browser opened successfully. Check the window.")
input("Press Enter to close...")
driver.quit()