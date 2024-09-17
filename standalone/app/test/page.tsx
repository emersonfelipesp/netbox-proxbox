import { Widget } from '@/components/Widget';

export default function Page() {

    <div className=" divide-y-2">
      
    <h2>Proxmox Clusters</h2>
    {
      proxmox_sessions.map(( cluster ) => (
        <ClusterCard cluster={cluster} />
      ))
    }
    <pre>{JSON.stringify(proxmox_sessions, null, 2)}</pre>
    <Widget />
    <div className="h-56 bg-slate-600 grid grid-cols-3 gap-4 content-around justify-center">
      <div className="bg-green-400">01</div>
      <div className="bg-green-400">02</div>
      <div className="bg-green-400">03</div>
      <div className="bg-green-400">04</div>
      <div className="bg-green-400">05</div>
    </div>
    <div class="flex justify-start">
      <div>01</div>
      <div>02</div>
      <div>03</div>
    </div>
    <div class="flex bg-slate-400 items-center ...">
      <div class="py-4">01</div>
      <div class="py-12">02</div>
      <div class="py-8">03</div>
    </div>
      <button type="button" class="bg-indigo-500 ..." disabled>
        <svg class="animate-spin h-5 w-5 mr-3 ..." viewBox="0 0 24 24">
        </svg>
        Processing...
      </button>

      
    <div>
      
    </div>
    
  </div>
}