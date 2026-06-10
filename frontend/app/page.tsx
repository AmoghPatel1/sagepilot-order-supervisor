import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">Sagepilot Order Supervisor</h1>
        <p className="text-gray-400 mb-8">AI-powered order lifecycle management</p>

        <div className="grid grid-cols-2 gap-4">
          <Link href="/supervisors"
            className="block p-6 bg-gray-900 border border-gray-800 rounded-lg hover:border-blue-500 transition-colors">
            <h2 className="text-xl font-semibold mb-2">Supervisors</h2>
            <p className="text-gray-400 text-sm">Configure supervisor templates</p>
          </Link>

          <Link href="/runs"
            className="block p-6 bg-gray-900 border border-gray-800 rounded-lg hover:border-blue-500 transition-colors">
            <h2 className="text-xl font-semibold mb-2">Runs</h2>
            <p className="text-gray-400 text-sm">View and manage active order runs</p>
          </Link>
        </div>
      </div>
    </main>
  );
}