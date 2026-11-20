import sys, os
root = "E:/DOWNLOADS/CREATIVE/PYTHON/GitHub/DOTA_MASTER"
sys.path.insert(0, root)
os.chdir(root)

from app import app
c = app.test_client()

r = c.get("/hero/Invoker")
print("Invoker hero page status:", r.status_code, "len:", len(r.data))
txt = r.get_data(as_text=True)
print("Invoker page has 'Контрптик':", "Контрптик" in txt)

r2 = c.get("/match/1000000")
print("match page status:", r2.status_code, "len:", len(r2.data))
m = r2.get_data(as_text=True)
print("match page has 'Контрптик':", "Контрптик" in m)
print("match page has 'Контрпик':", "Контрпик" in m)

r3 = c.get("/")
print("index status:", r3.status_code)
