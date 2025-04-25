with open("src/bot/states.py", "r") as f:
    content = f.read()
content = content.replace("State() %", "State()")
with open("src/bot/states.py", "w") as f:
    f.write(content)
print("File fixed!") 