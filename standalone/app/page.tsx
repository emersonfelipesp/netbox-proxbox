import Image from 'next/image'
import Link from 'next/link'
import Widget from '@/components/Widget'

import { Circle } from 'lucide-react'

// const clusters = [
//   {
//     "domain": "10.0.30.9",
//     "http_port": 8006,
//     "user": "root@pam",
//     "name": "PVE-CLUSTER-02",
//     "mode": "cluster"
//   },
//   {
//     "domain": "10.0.30.139",
//     "http_port": 8006,
//     "user": "root@pam",
//     "name": "pve01proxbox",
//     "mode": "standalone"
//   }
// ]

function ClusterCard({ cluster }) {

  return (
    <div className="flex flex-row divide-black">
      <div className="flex-auto flex-col py-4">
        {/* Row 1 */}
        <div class="flex gap-x-4 pl-4 mb-3">
            <div><Circle /></div>
            <div className="">{cluster.name}</div>
            <div>/</div>
            <div className="">{cluster.domain}:{cluster.http_port}</div>
        </div>
        {/* Row 2 */}
        <div class="flex gap-x-4 pl-4">
          <div className="">{cluster.user}</div>
        </div>

      </div>
      <div className= "flex-none mx-2 my-5 rounded-full p-3 mr-3 order-last bg-slate-500"><span>{cluster.mode}</span></div>
    </div>
  )
}

export default async function Home() {
  const response = await fetch('http://localhost:8800/proxmox/sessions', {
    next: {
      revalidate: 30,
    }
  })
  
  const proxmox_sessions = await response.json()

  return (
    <div className="p-5 divide-y-2">
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
    </div>
    
  )
}
