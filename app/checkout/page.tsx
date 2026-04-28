'use client';

import React, { useState } from 'react';
import { Shield, Zap, Globe, CreditCard } from 'lucide-react';

export default function SolanaCheckout() {
  const [amount, setAmount] = useState('100'); // Default 100 USDC for 1% fee downpayment
  const walletAddress = "FTg2aAtrZ2QePFiQHExzTJESZnwMT82Jr6aETm6ni57q"; // Your Solana Wallet

  const handlePay = () => {
    // Generates a Solana Pay URL
    const memo = "Empire_AI_Whale_Fee";
    const solanaUrl = `solana:${walletAddress}?amount=${amount}&label=Empire%20AI%20Fee&message=${memo}`;
    window.location.href = solanaUrl;
  };

  return (
    <div className="min-h-screen bg-black text-white font-mono flex flex-col items-center justify-center p-6">
      <div className="max-w-2xl w-full border-2 border-blue-500 p-8 bg-zinc-950 shadow-[0_0_50px_rgba(37,99,235,0.2)]">
        <div className="flex justify-between items-center mb-10">
          <h1 className="text-4xl font-black italic tracking-tighter text-blue-500">EMPIRE CHECKOUT</h1>
          <div className="animate-pulse flex items-center gap-2 text-green-500 text-xs">
            <div className="h-2 w-2 bg-green-500 rounded-full" />
            SOLANA MAINNET ACTIVE
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-10">
          <div className="space-y-4">
            <p className="text-zinc-500 uppercase text-xs tracking-widest">Service</p>
            <h2 className="text-xl font-bold">1% Whale Success Fee</h2>
            <p className="text-zinc-400 text-sm">
              Secures your exclusive access to the satellite-soured warehouse lead block and initiates the 
              automated closing sequence.
            </p>
          </div>
          <div className="bg-zinc-900 p-6 border border-zinc-800">
            <p className="text-zinc-500 uppercase text-xs tracking-widest mb-2">Total Due</p>
            <div className="text-4xl font-black text-white flex items-baseline gap-2">
              <input 
                type="number" 
                value={amount} 
                onChange={(e) => setAmount(e.target.value)}
                className="bg-transparent border-b border-blue-500 w-24 outline-none text-blue-400"
              /> 
              <span className="text-xl">USDC</span>
            </div>
          </div>
        </div>

        <button 
          onClick={handlePay}
          className="w-full bg-blue-600 hover:bg-blue-500 text-white py-6 text-2xl font-black flex items-center justify-center gap-4 transition-all hover:scale-[1.02]"
        >
          <CreditCard className="w-8 h-8" />
          PAY WITH TOKEN POCKET
        </button>

        <div className="mt-10 grid grid-cols-3 gap-4 text-center border-t border-zinc-800 pt-8">
          <div className="flex flex-col items-center gap-2">
            <Shield className="text-blue-500 w-5 h-5" />
            <span className="text-[10px] text-zinc-600 uppercase">Secure</span>
          </div>
          <div className="flex flex-col items-center gap-2">
            <Zap className="text-yellow-500 w-5 h-5" />
            <span className="text-[10px] text-zinc-600 uppercase">Instant</span>
          </div>
          <div className="flex flex-col items-center gap-2">
            <Globe className="text-green-500 w-5 h-5" />
            <span className="text-[10px] text-zinc-600 uppercase">Verified</span>
          </div>
        </div>
      </div>

      <p className="mt-8 text-zinc-800 text-[10px] uppercase tracking-[0.5em]">
        Empire AI Settlement Protocol v2.0
      </p>
    </div>
  );
}
