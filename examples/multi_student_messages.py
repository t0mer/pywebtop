import asyncio
import sys
import os

# Add the parent directory to sys.path to import the webtop package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from webtop import WebtopClient, WebtopLoginError

async def main():
    USERNAME = "<username>"
    PASSWORD = "<password>"

    print(f"Attempting to login as {USERNAME}...")

    try:
        async with WebtopClient(username=USERNAME, password=PASSWORD) as client:
            session = await client.login()
            print(f"✅ Logged in successfully!")
            print(f"Name: {session.first_name} {session.last_name}")
            
            # --- AUTO-DISCOVER STUDENTS ---
            print("\nDiscovering all students...")
            students = await client.get_linked_students()
            print(f"Found {len(students)} students linked to this account.")
            
            for i, student in enumerate(students):
                # The 'GetMultipleUsersForUser' response contains 'studentLogin' and 'school_name', but not full name.
                name_hint = student.get('studentLogin', 'Unknown')
                school_name = student.get('school_name', 'Unknown School')
                print(f"\n--- Linked Account {i+1}: {name_hint} ({school_name}) ---")

                s_id = student.get('studentId')
                school = student.get('school_name')
                
                # Check if this is the current session
                if s_id == session.student_id:
                     print(f" (Current Session: {school})")
                
                print(f"Switching to {school}...")
                
                try:                    
                     new_session = await client.switch_student(student_id=s_id, saved_user="") 
                     # The session might show the Parent's name (Arik). 
                     # We need to get the dashboard to find the actual Student's name (Eden/Or).
                     
                     dashboard = await client.get_students()
                     student_name = "Unknown"
                     if isinstance(dashboard, dict) and 'data' in dashboard:
                         data = dashboard['data']
                         if isinstance(data, dict) and 'childrens' in data:
                             children = data['childrens']
                             if isinstance(children, list) and len(children) > 0:
                                 child = children[0]
                                 student_name = f"{child.get('firstName')} {child.get('lastName')}"

                     print(f"✅ Switched to session for: {student_name} (School: {new_session.school_name})")
                     
                     print(f"Fetching messages for {student_name}...")
                     await fetch_and_print_messages(client)
                     
                except Exception as e:
                    print(f"Failed to switch to {school}: {e}")

    except WebtopLoginError as e:
        print(f"❌ Login failed: {e}")
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        import traceback
        traceback.print_exc()

async def fetch_and_print_messages(client):
    try:
        messages_resp = await client.get_messages_inbox(page_id=1)
        if isinstance(messages_resp, dict) and 'data' in messages_resp:
            messages = messages_resp['data']
            print(f"Found {len(messages)} messages.")
            
            for i, msg in enumerate(messages[:20]):
                f_name = msg.get('student_F_name', '')
                l_name = msg.get('student_L_name', '')
                sender = f"{f_name} {l_name}".strip() or msg.get('senderName') or 'Unknown'
                subject = msg.get('subject', 'No Subject')
                date = msg.get('sendingDate') or msg.get('msgTime') or ''
                print(f"{i+1}. [{date}] {sender}: {subject}")
        else:
             print(f"Message response has unexpected format.")
    except Exception as e:
        print(f"Failed to fetch messages: {e}")

if __name__ == "__main__":
    if asyncio.get_event_loop_policy().get_event_loop().is_closed():
         asyncio.set_event_loop(asyncio.new_event_loop())
    asyncio.run(main())
