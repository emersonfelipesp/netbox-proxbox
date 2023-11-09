import Image from 'next/image'
import Link from 'next/link'

export default function Home() {
  return (
    <div className="mx-auto max-w-xs">
      <div >
        <h1 className="text-3x1 font-bold underline">Welcome to Proxmox Standalone Version!</h1>
      </div>
      
      <ul>
        <li><Link href="/cluster">Clusters</Link></li>
        <li><Link href="/proxmox/sessions">Proxmox Sessions</Link></li>
      </ul>

      <a href="#" className="group block max-w-xs mx-auto rounded-lg p-6 bg-white ring-1 ring-slate-900/5 shadow-lg space-y-3 hover:bg-sky-500 hover:ring-sky-500">
        <div className="flex items-center space-x-3">
          <svg className="h-6 w-6 stroke-sky-500 group-hover:stroke-white" fill="none" viewBox="0 0 24 24"></svg>
          <h3 className="text-slate-900 group-hover:text-white text-sm font-semibold">Proxmox Sessions</h3>
        </div>
        <p className="text-slate-500 group-hover:text-white text-sm">View all Proxmox </p>
      </a>
    </div>
      
  )

}
