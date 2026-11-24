import React, { useState } from 'react'

function App() {
  const [activeTab, setActiveTab] = useState('upload')

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-blue-900 text-white p-4">
        <div className="container mx-auto">
          <h1 className="text-2xl font-bold">FINTRACE - Money Trail Analysis</h1>
          <p className="text-sm text-blue-200">Rajasthan Police Hackathon 2026 - PS05</p>
        </div>
      </nav>

      <div className="container mx-auto p-6">
        <div className="bg-white rounded-lg shadow-lg p-6">
          <div className="flex space-x-4 mb-6 border-b">
            <button
              onClick={() => setActiveTab('upload')}
              className={`pb-2 px-4 ${activeTab === 'upload' ? 'border-b-2 border-blue-600 font-semibold' : 'text-gray-600'}`}
            >
              Upload Statements
            </button>
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`pb-2 px-4 ${activeTab === 'dashboard' ? 'border-b-2 border-blue-600 font-semibold' : 'text-gray-600'}`}
            >
              Dashboard
            </button>
          </div>

          {activeTab === 'upload' && (
            <div className="space-y-4">
              <h2 className="text-xl font-semibold mb-4">Upload Bank Statements</h2>

              <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
                <svg className="mx-auto h-12 w-12 text-gray-400" stroke="currentColor" fill="none" viewBox="0 0 48 48">
                  <path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <p className="mt-2 text-sm text-gray-600">Drop statement files here or click to browse</p>
                <p className="text-xs text-gray-500 mt-1">Supports CSV, XLSX, PDF</p>
                <input type="file" multiple className="mt-4" accept=".csv,.xlsx,.pdf" />
              </div>

              <button className="w-full bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700">
                Analyze Case
              </button>

              <div className="mt-6 p-4 bg-green-50 border border-green-200 rounded">
                <h3 className="font-semibold text-green-900">Demo Instructions:</h3>
                <ol className="text-sm text-green-800 mt-2 space-y-1 list-decimal list-inside">
                  <li>Sample data available in <code className="bg-white px-1 rounded">sample_data/case_001/</code></li>
                  <li>Upload CSV, XLSX, and PDF files from that folder</li>
                  <li>Click Analyze to run full pipeline</li>
                  <li>View results in Dashboard tab</li>
                </ol>
              </div>
            </div>
          )}

          {activeTab === 'dashboard' && (
            <div className="space-y-6">
              <h2 className="text-xl font-semibold">Analysis Dashboard</h2>

              <div className="grid grid-cols-4 gap-4">
                <div className="bg-blue-50 p-4 rounded border border-blue-200">
                  <div className="text-sm text-blue-600">Total Accounts</div>
                  <div className="text-2xl font-bold">64</div>
                </div>
                <div className="bg-red-50 p-4 rounded border border-red-200">
                  <div className="text-sm text-red-600">Mule Accounts</div>
                  <div className="text-2xl font-bold">58</div>
                </div>
                <div className="bg-green-50 p-4 rounded border border-green-200">
                  <div className="text-sm text-green-600">Traced Amount</div>
                  <div className="text-2xl font-bold">₹1.5L</div>
                </div>
                <div className="bg-orange-50 p-4 rounded border border-orange-200">
                  <div className="text-sm text-orange-600">Est. Recovery</div>
                  <div className="text-2xl font-bold">₹85K</div>
                </div>
              </div>

              <div className="bg-gray-100 h-64 rounded flex items-center justify-center border-2 border-dashed">
                <div className="text-center">
                  <p className="text-gray-500">Transaction Graph Visualization</p>
                  <p className="text-sm text-gray-400 mt-2">Cytoscape.js graph would render here</p>
                  <p className="text-xs text-gray-400 mt-1">(Red = High suspicion, Orange = Medium, Grey = Normal)</p>
                </div>
              </div>

              <div>
                <h3 className="font-semibold mb-3">Freeze Priority Rankings</h3>
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-100 border-b">
                      <th className="p-2 text-left">Rank</th>
                      <th className="p-2 text-left">Account</th>
                      <th className="p-2 text-left">Suspicion</th>
                      <th className="p-2 text-left">Est. Recovery</th>
                      <th className="p-2 text-left">Time Critical</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b hover:bg-gray-50">
                      <td className="p-2">1</td>
                      <td className="p-2 font-mono text-sm">AXIS_ACCOUNT_0085579</td>
                      <td className="p-2"><span className="bg-red-100 text-red-800 px-2 py-1 rounded text-sm">64.2</span></td>
                      <td className="p-2 font-semibold">₹25,000</td>
                      <td className="p-2">0.95</td>
                    </tr>
                    <tr className="border-b hover:bg-gray-50">
                      <td className="p-2">2</td>
                      <td className="p-2 font-mono text-sm">ICICI_ACCOUNT_B0BC19</td>
                      <td className="p-2"><span className="bg-red-100 text-red-800 px-2 py-1 rounded text-sm">63.1</span></td>
                      <td className="p-2 font-semibold">₹18,500</td>
                      <td className="p-2">0.88</td>
                    </tr>
                    <tr className="border-b hover:bg-gray-50">
                      <td className="p-2">3</td>
                      <td className="p-2 font-mono text-sm">SBI_ACCOUNT_E05DD18C</td>
                      <td className="p-2"><span className="bg-orange-100 text-orange-800 px-2 py-1 rounded text-sm">63.1</span></td>
                      <td className="p-2 font-semibold">₹15,200</td>
                      <td className="p-2">0.82</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <button className="bg-red-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-red-700">
                Download PDF Report
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
