import Image from 'next/image'
import Link from 'next/link'

export default function Home() {
  return (
    <>
    <div className="container mx-auto">
      <h1>Proxbox</h1>
      <div className="grid grid-flow-col grid-col-3 grid-rows-2 gap-4 bg-slate-400 rounded-lg justifiy-around">
        
        <div className="col-span-2 self-center pl-4 pt-3">
          <div className="flex justify-start">
            <span>Status</span>
            <span className="inline-block ml-4">Domain</span>
            <span className="inline-block ml-4">IP</span>
          </div>
        </div>
        <div className="col-span-2 self-center pl-4 pb-3">Linha 01</div>
        <div className="grid-start-2 row-span-2 self-center mx-auto">Cluster</div>
      </div>
    </div>
      <div className="lg:container mx-auto">
        <h1>Proxbox</h1>
        <div className="grid grid-flow-col grid-rows-2 gap-4 bg-slate-400 rounded-lg justifiy-around">
          
          <div>Col 2</div>
          <div>Col 3</div>
          <div>Col 4</div>
          <div>Col 5</div>
          <div className="row-span-2 self-center mx-auto">Standalone</div>
        </div>
      </div>
    </>
  )

}
