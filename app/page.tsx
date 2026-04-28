import UglyBanner from '@/components/UglyBanner';

export default function Home() {
  // This will eventually come from Vercel Edge Config or Supabase
  const bannerConfig = {
    copy: "URGENT PLUMBING EMERGENCY? DON'T WAIT!",
    bgColor: "#FFFF00",
    textColor: "#FF0000",
    phone: "1-800-EMPIRE-01",
    variantId: "control_v1"
  };

  return (
    <main className="min-h-screen bg-white">
      <UglyBanner config={bannerConfig} />
      
      <div className="max-w-4xl mx-auto p-8 prose prose-xl">
        <h2 className="text-3xl font-bold mt-8">Why Choose Empire AI Plumbing?</h2>
        <p>
          We are the fastest responding service in the area. Our AI-driven dispatch system ensures 
          that the closest technician is sent to your door within minutes, not hours.
        </p>
        
        <ul className="list-disc pl-5 space-y-4 mt-4">
          <li><strong>24/7 Service:</strong> We never sleep, so you can.</li>
          <li><strong>Flat Rates:</strong> No hidden fees, ever.</li>
          <li><strong>Licensed Pros:</strong> Only the best of the best.</li>
        </ul>

        <div className="bg-gray-100 p-6 rounded-xl mt-12 border-2 border-gray-300">
          <p className="font-bold">"Empire AI saved my basement from a total flood. They were here in 15 minutes!"</p>
          <span className="text-sm">- Satisfied Customer</span>
        </div>
      </div>

      <div className="mt-20">
         <UglyBanner config={bannerConfig} />
      </div>
    </main>
  );
}
