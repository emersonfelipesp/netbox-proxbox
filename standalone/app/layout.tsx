import Head from 'next/head'
import type { Metadata } from 'next'
 
// These styles apply to every route in the application
import './globals.css'
import Page from './cluster/page'
 
export const metadata: Metadata = {
  title: 'Proxbox App',
  description: 'The Proxbox Standalone Version!',
}

function LogoNavbar() {
  return (
    <>
      <a href="https://github.com/netdevopsbr/netbox-proxbox" className="flex items-center">
            <span className="font-extrabold text-5xl bg-clip-text text-transparent bg-gradient-to-r from-orange-700 to-blue-800 dark:text-white">proxbox</span>
      </a>
    </>
  )
}

function Navbar() {
  return (
    <nav className="bg-white border-gray-200 dark:bg-gray-900">
      <div className="max-w-screen-xl flex flex-wrap items-center justify-between mx-auto p-4 ">
        <LogoNavbar />
        <button data-collapse-toggle="navbar-default" type="button" className="inline-flex items-center p-2 w-10 h-10 justify-center text-sm text-gray-500 rounded-lg md:hidden hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-200 dark:text-gray-400 dark:hover:bg-gray-700 dark:focus:ring-gray-600" aria-controls="navbar-default" aria-expanded="false">
            <span className="sr-only">Open main menu</span>
            <svg className="w-5 h-5" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 17 14">
                <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M1 1h15M1 7h15M1 13h15"/>
            </svg>
        </button>
        <div className="hidden w-full md:block md:w-auto" id="navbar-default">
          <ul className="font-medium flex flex-col p-4 md:p-0 mt-4 border border-gray-100 rounded-lg bg-gray-50 md:flex-row md:space-x-8 md:mt-0 md:border-0 md:bg-white dark:bg-gray-800 md:dark:bg-gray-900 dark:border-gray-700">
            <li>
              <a href="https://github.com/netdevopsbr/netbox-proxbox" className="block py-2 pl-3 pr-4 text-gray-900 rounded hover:bg-gray-100 md:hover:bg-transparent md:border-0 md:hover:text-blue-700 md:p-0 dark:text-white md:dark:hover:text-blue-500 dark:hover:bg-gray-700 dark:hover:text-white md:dark:hover:bg-transparent">GitHub</a>
            </li>
            <li>
              <a href="https://docs.netbox.dev.br/" className="block py-2 pl-3 pr-4 text-gray-900 rounded hover:bg-gray-100 md:hover:bg-transparent md:border-0 md:hover:text-blue-700 md:p-0 dark:text-white md:dark:hover:text-blue-500 dark:hover:bg-gray-700 dark:hover:text-white md:dark:hover:bg-transparent">Docs</a>
            </li>
          </ul>
        </div>
      </div>
    </nav>
  )
}

function Sidebar() {
  return (
    <>
      <div className="h-screen w-64 bg-black text-white">
        <ul><li key="something">teste</li></ul>
      </div>
    </>
  )
}

function MainContent({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1 flex flex-col">
      {children}
    </div>
  )
}

function PageContent({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1">
      {children}
    </div>
  )
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen flex">
        <Sidebar />
        <MainContent>
          <Navbar />
          <PageContent>
            {children}
          </PageContent>
        </MainContent>
      </body>
    </html>  
  )
}