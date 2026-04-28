'use client';

import React from 'react';

interface UglyBannerProps {
  config: {
    copy: string;
    bgColor: string;
    textColor: string;
    phone: string;
    variantId: string;
  };
}

export default function UglyBanner({ config }: UglyBannerProps) {
  const handleCall = async () => {
    // In a real scenario, we'd log the click to Supabase before the call starts
    console.log(`Tracking call for variant: ${config.variantId}`);
    try {
      // Future: fetch('/api/track-call', { method: 'POST', body: JSON.stringify({ variantId: config.variantId }) });
    } catch (e) {
      console.error('Failed to log call click', e);
    }
  };

  return (
    <div 
      className="w-full p-8 text-center border-[10px] border-dashed border-red-600 animate-pulse"
      style={{ 
        backgroundColor: config.bgColor || '#FFFF00', 
        color: config.textColor || '#FF0000'
      }}
    >
      <h1 className="text-4xl md:text-6xl font-black mb-4 uppercase tracking-tighter">
        {config.copy}
      </h1>
      <p className="text-2xl font-bold mb-6 italic underline">
        WE ARE OPEN 24/7 - CALL THE HOTLINE NOW!
      </p>
      <a 
        href={`tel:${config.phone}`}
        onClick={handleCall}
        className="inline-block bg-black text-white px-10 py-6 text-3xl font-black rounded-none hover:scale-110 transition-transform"
      >
        CLICK TO CALL: {config.phone}
      </a>
      <div className="mt-4 text-sm font-mono opacity-70">
        Tracking ID: {config.variantId}
      </div>
    </div>
  );
}
