import Link from 'next/link';

export default function SessionItemRoot({ cluster, children }) {
    return (
      <div>
      <Link href={`/proxmox/${cluster.name}`}>
        <div className="hover:bg-slate-50 flex flex-row">
          
            <div className="flex-auto flex-col py-4">
              {/* Row 1 */}
              <div class="flex gap-x-4 pl-4 mb-3 items-center font-bold">

                  {/* Status Placeholder */}
                  { children }

                  <div className="">{cluster.name}</div>
                  <div>/</div>
                  <div className="">{cluster.domain} : {cluster.http_port}</div>
              </div>
              {/* Row 2 */}
              <div className="flex gap-x-4 pl-4">
                <div className="">{cluster.user}</div>
              </div>
      
            </div>
            {/* Cluster Mode Badge */}
            <div className= "flex-none mx-2 my-5 rounded-3xl self-center p-2 mr-3 order-last bg-amber-400 text-white text-lg "><span>{cluster.mode}</span></div>
          
        </div>
        </Link >
      </div>

    )
}