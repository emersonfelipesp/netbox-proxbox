import { X, Check } from 'lucide-react'

interface NotificationActionsProps {
    children: React.ReactNode
}

export function NotificationActions ({ children }: NotificationActionsProps) {
    return (
        <div className="flex gap-2 self-center">

            {children}
            
            {/* <button  className="w-8 h-8 rounded flex items-center justify-center bg-violet-400 hover:bg-violet-500 dark:bg-violet-800">
                <Check className="w-3 h-3 text-zinc-50" />
            </button> */}
        </div>
    )
}