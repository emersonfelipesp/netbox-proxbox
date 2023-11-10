import Image from 'next/image'
import Link from 'next/link'


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
    <div className="grid grid-flow-col grid-col-3 grid-rows-2 gap-4 bg-slate-400 rounded-lg justifiy-around">
      <div className="col-span-2 self-center pl-4 pt-3">
        <div className="flex justify-start">
          <span>Status</span>
          <span className="inline-block ml-4">{cluster.domain}</span>
          <span className="inline-block ml-4">{cluster.http_port}</span>
        </div>
      </div>
      <div className="col-span-2 self-center pl-4 pb-3">{cluster.name}</div>
      <div className="grid-start-2 row-span-2 self-center mx-auto">{cluster.mode}</div>
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
    <>
      {
        proxmox_sessions.map(( cluster ) => (
          <ClusterCard cluster={cluster} />
        ))
      }
      <pre>{JSON.stringify(proxmox_sessions, null, 2)}</pre>
    </>
  )
}
