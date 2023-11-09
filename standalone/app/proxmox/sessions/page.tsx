async function getData() {
    const res = await fetch('http://localhost:8800/proxmox/sessions', {
        'headers': {
            'Content-Type': 'application/json',
        }
    })

    if (!res.ok) {
        // This will activate the closest `error.js` Error Boundary
        throw new Error('Failed to fetch data')
    }

    return res.json()
}


async function Session({ sessions }) {

    return (
        <div>
            {
                sessions.map(( session ) => (
                    <>
                        <a href="#" className="group block max-w-xs mx-auto rounded-lg p-6 bg-white ring-1 ring-slate-900/5 shadow-lg space-y-3 hover:bg-sky-500 hover:ring-sky-500">
                            <div className="flex items-center space-x-3">
                                <svg className="h-6 w-6 stroke-sky-500 group-hover:stroke-white" fill="none" viewBox="0 0 24 24"></svg>
                                <h3 className="text-slate-900 group-hover:text-white text-sm font-semibold">{session.name}</h3>
                            </div>
                            <h2 className="text-slate-500 group-hover:text-white text-sm">View all Proxmox </h2>
                        </a>
                        <ul>
                                <li key={session.domain}>{session.domain}</li>
                                <li key={session.http_user}>{session.http_user}</li>
                                <li key={session.user}>{session.user}</li>
                                <li key={session.name}>{session.name}</li>
                                <li key={session.mode}>{session.mode}</li>
                        </ul>
                    </>
                ))
            }
        </div>
    )
        
    
}
export default async function Page() {
    const data = await getData()

    return (
        <div className="container mx-auto max-w-xs">
            <h1>Proxmox Sessions</h1>
            <Session sessions={data} />
        </div>  
    )
}