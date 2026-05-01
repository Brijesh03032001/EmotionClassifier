"use client";

import Navbar from "@/components/Navbar";
import HeroSection from "@/components/HeroSection";
import MoodBrowse from "@/components/MoodBrowse";
import BottomPlayer from "@/components/BottomPlayer";
import Footer from "@/components/Footer";

export default function Home() {
  function handleMoodSelect(mood: string) {
    document.getElementById("discover")?.scrollIntoView({ behavior: "smooth" });
    setTimeout(() => {
      const textarea = document.querySelector<HTMLTextAreaElement>("textarea");
      if (textarea) {
        // Trigger React's synthetic onChange by using native input event
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype,
          "value"
        )?.set;
        nativeInputValueSetter?.call(textarea, `Give me some ${mood} music`);
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
        textarea.focus();
      }
    }, 600);
  }

  return (
    <>
      <Navbar />
      <main className="flex flex-col items-center w-full">
        <HeroSection />
        <MoodBrowse onSelect={handleMoodSelect} />
        <Footer />
      </main>
      <BottomPlayer />
    </>
  );
}

