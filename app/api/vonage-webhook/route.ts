import { NextResponse } from 'next/server';
import { supabase } from '@/lib/supabase';

export async function POST(req: Request) {
  const data = await req.json();
  
  // Vonage Webhook Payload (simplified)
  const { 
    uuid, 
    from, 
    to, 
    status, 
    direction,
    timestamp 
  } = data;

  if (direction === 'inbound') {
    // Log the call in Supabase
    const { error } = await supabase
      .from('calls')
      .insert({
        vonage_call_id: uuid,
        from_number: from,
        to_number: to,
        status: status,
        created_at: timestamp
      });

    if (error) {
      console.error('Error logging call to Supabase:', error);
      return NextResponse.json({ error: 'Database log failed' }, { status: 500 });
    }
  }

  return NextResponse.json({ success: true });
}
