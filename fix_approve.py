with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

old = """        threading.Thread(
            target=self.send_appointment_email,
            args=(patient_email, fullname, action, data),
            daemon=True
        ).start()
    
        return f"Appointment {action}ed"
    except Exception as e:
        print(f"{action.capitalize()} error: {e}")
        return f"Failed to {action} appointment: {e}", 500"""

new = """        threading.Thread(
            target=self.send_appointment_email,
            args=(patient_email, fullname, action, data),
            daemon=True
        ).start()

        threading.Thread(
            target=self.send_push_notification,
            args=(uid, fullname, action, data),
            daemon=True
        ).start()
    
        return f"Appointment {action}ed"
    except Exception as e:
        print(f"{action.capitalize()} error: {e}")
        return f"Failed to {action} appointment: {e}", 500"""

if old in content:
    content = content.replace(old, new)
    with open("main.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Added push notification call to main.py approve method")
else:
    print("Pattern not found - checking with relaxed whitespace")
    # Try with flexible whitespace
    import re
    pattern = r'(threading\.Thread\(\s*target=self\.send_appointment_email.*?\.start\(\)\s*return f"Appointment \{action\}ed")'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        print("Found match with regex")
    else:
        print("Could not find pattern to replace")
