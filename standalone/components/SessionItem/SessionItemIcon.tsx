import clsx from 'clsx';

type SessionStatus = "running" | "stopped" | "error" | "unknown"

interface SessionItemIconProps {
    status: SessionStatus
}

export default function SessionItemIcon({ status }: SessionItemIconProps) {
    return (
        <div>
            <span className="relative flex h-3 w-3">
                <span className={clsx(
                    "animate-ping absolute inline-flex h-full w-full rounded-full opacity-75",
                        {
                            "bg-gray-400": status === "unknown",
                            "bg-red-400": status === "stopped" || status  === "error",
                            "bg-green-400": status === "running",
                        },
                    )}>
                </span>

                <span className={clsx(
                    "relative inline-flex rounded-full h-3 w-3",
                        {
                            "bg-gray-500": status === "unknown",
                            "bg-red-500": status === "stopped" || status  === "error",
                            "bg-green-500": status === "running",
                        },
                    )}>
                </span>
            </span>
            

        </div>
    )
}