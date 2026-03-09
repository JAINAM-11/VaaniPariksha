
import asyncio
import edge_tts
import os

ssml_content = """
Welcome to VaaniPariksha — a revolutionary AI-powered voice examination platform designed to provide a truly independent and accessible testing experience for visually impaired students.
<break time="2000ms"/>
We begin at the Admin Dashboard, which provides a comprehensive overview of exams and live student monitoring.
<break time="1000ms"/>
Navigating to the upload section, the examiner can easily transform traditional PDF papers into interactive, voice-navigable exams.
<break time="1000ms"/>
Simply drag and drop your exam PDF into the secure portal.
<break time="1000ms"/>
Next, we define the exam details. We'll set the title to Sample Test 2026 and establish a duration of sixty minutes for the session.
<break time="3000ms"/>
Our AI extraction layer now takes over, parsing the PDF to identify questions, marks, and options with total accuracy.
<break time="1000ms"/>
Success! The exam is now successfully processed and listed in the All Exams section, ready for students to begin.
<break time="4000ms"/>
Switching to the student view, we can see the listed exams. The interface is optimized for high contrast and accessibility.
<break time="1000ms"/>
The student selects Take Exam to begin their session.
<break time="1000ms"/>
The system first asks for the Student ID. The student speaks their ID, which the AI confirms: I heard Student ID Two-Four-One-Five-Three. Is that correct? Once confirmed, the system greets the student and prepares the environment. When the student says Begin Exam, the session officially starts.
<break time="5000ms"/>
Question one. What is the capital of France? Option A: Berlin. Option B: Madrid. Option C: Paris. Option D: Rome.
<break time="1000ms"/>
The student says Option C. The system responds: You selected Option C, Paris. Shall I save this? 
<break time="1000ms"/>
The student confirms with Yes, and the answer is securely stored. VaaniPariksha handles all question types — from MCQs and True-False to complex descriptive answers which can be modified entirely via voice. 
<break time="1000ms"/>
With commands for navigation, status checks, and speech speed, VaaniPariksha empowers every student with autonomy. 
Independence starts here.
"""

full_ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
<voice name="en-US-GuyNeural">
{ssml_content}
</voice>
</speak>"""

OUTPUT_FILE = "vaanipariksha_voiceover.mp3"

async def main():
    print("Generating voiceover...")
    communicate = edge_tts.Communicate(full_ssml)
    await communicate.save(OUTPUT_FILE)
    print(f"File saved to {os.path.abspath(OUTPUT_FILE)}")

if __name__ == "__main__":
    asyncio.run(main())
