import "./App.css";
import React, { useEffect, useState } from "react";
import axios from "axios";

export default function App() {
  const [people, setPeople] = useState([]);
  const [editId, setEditId] = useState(null);
  const [replication, setReplication] = useState({});
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [history, setHistory] = useState([]);
  const [showHistoryId, setShowHistoryId] = useState(null);
  const [isNodeDown, setIsNodeDown] = useState(false);

  const API = "http://127.0.0.1:5000";

  const loadPeople = async () => {
    try {
      const res = await axios.get(`${API}/people`);
      setPeople(res.data);
    } catch (err) {
      console.error("Lỗi khi gọi API:", err);
    }
  };

  const loadReplicationStatus = async () => {
    try {
      const res = await axios.get(`${API}/replication-status`);
      setReplication(res.data);
    } catch (err) {
      console.error("Lỗi lấy replication:", err);
    }
  };

  useEffect(() => {
    loadPeople();
    loadReplicationStatus();
  }, []);

  // ==== Undo / Redo / CRUD ====
  const undoPerson = async (id) => {
    try {
      const res = await axios.post(`${API}/people/${id}/undo`);
      loadPeople();
      setHistory(res.data.history);
      setShowHistoryId(id);
    } catch (err) {
      alert("Không thể undo: " + err.response.data.error);
    }
  };

  const redoPerson = async (id) => {
    try {
      const res = await axios.post(`${API}/people/${id}/redo`);
      loadPeople();
      setHistory(res.data.history);
      setShowHistoryId(id);
    } catch (err) {
      alert("Không thể redo: " + err.response.data.error);
    }
  };

  const viewHistory = async (id) => {
    try {
      const res = await axios.get(`${API}/people/${id}/history`);
      setHistory(res.data);
      setShowHistoryId(id);
    } catch {
      alert("Không có lịch sử cho " + id);
    }
  };

  const deletePerson = async (id) => {
    await axios.delete(`${API}/people/${id}`);
    loadPeople();
  };

  const startEdit = (p) => {
    setEditId(p.id);
    setName(p.name);
    setAge(p.age);
    setShowForm(true);
  };

  const addPerson = async () => {
    if (!name || !age) return alert("Nhập đủ thông tin");
    await axios.post(`${API}/people`, { name, age: parseInt(age) });
    setName("");
    setAge("");
    setShowForm(false);
    loadPeople();
  };

  const updatePerson = async () => {
    if (!editId) return;
    await axios.put(`${API}/people/${editId}`, {
      name,
      age: parseInt(age),
    });
    setEditId(null);
    setName("");
    setAge("");
    setShowForm(false);
    loadPeople();
  };

  const openAddForm = () => {
    setEditId(null);
    setName("");
    setAge("");
    setShowForm(true);
  };

  const closeForm = () => {
    setEditId(null);
    setName("");
    setAge("");
    setShowForm(false);
  };

  // ==== Phân tán ====
  const runReplication = async () => {
    try {
      const res = await axios.post(`${API}/run-replication`, {
        nodes: ["node_A", "node_B", "node_C"],
      });
      console.log("Replication:", res.data);
      loadReplicationStatus();
      alert("Replication đã khởi chạy!");
    } catch {
      alert("Lỗi replication");
    }
  };

  const disconnectNode = async () => {
    try {
      await axios.post(`${API}/failover/disconnect`);
      setIsNodeDown(true);
      alert("Node chính đã bị ngắt kết nối!");
    } catch {
      alert("Lỗi khi ngắt kết nối node chính");
    }
  };

  const reconnectNode = async () => {
    try {
      await axios.post(`${API}/failover/reconnect`);
      setIsNodeDown(false);
      alert("Node chính đã được khôi phục!");
    } catch {
      alert("Lỗi khi khôi phục node chính");
    }
  };

  return (
    <div className="app-container">
      <nav className="navigator">
        <button>Danh sách nhân viên</button>
        <button>Danh sách khách hàng</button>
      </nav>

      <div className="content">
        <h2> Danh sách nhân viên</h2>
        <div className="replication-status">
          <h4>Replication Status</h4>
          {Object.entries(replication).map(([node, status]) => (
            <div key={node} className={`status-item ${status}`}>
              <span className="node-name">{node}</span>
              <span className="status-icon">
                {status === "synced"
                  ? "✔️"
                  : status === "pending"
                  ? "⏳"
                  : "❌"}
              </span>
              <span className="status-text">
                {status === "synced"
                  ? "Đã đồng bộ"
                  : status === "pending"
                  ? "Đang đồng bộ"
                  : "Lỗi"}
              </span>
            </div>
          ))}
          <div className="replication-buttons">
            <button onClick={runReplication} className="btn-replicate">
              🔄 Chạy Replication
            </button>
            <button
              onClick={disconnectNode}
              className="btn-fail"
              disabled={isNodeDown}
            >
              ❌ Mất kết nối node chính
            </button>
            <button
              onClick={reconnectNode}
              className="btn-recover"
              disabled={!isNodeDown}
            >
              ✅ Khôi phục node chính
            </button>
          </div>
        </div>

        <button className="btn-add" onClick={openAddForm}>
          Thêm nhân viên
        </button>
        {people.length === 0 ? (
          <p>Chưa có dữ liệu trong ZODB</p>
        ) : (
          <table className="people-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Tên</th>
                <th>Tuổi</th>
                <th>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {people.map((p) => (
                <tr key={p.id} className="tr">
                  <td>{p.id}</td>
                  <td>{p.name}</td>
                  <td>{p.age}</td>
                  <td>
                    <button
                      onClick={() => deletePerson(p.id)}
                      className="btn-delete"
                    >
                      Xóa
                    </button>
                    <button onClick={() => startEdit(p)} className="btn-edit">
                      Sửa
                    </button>
                    <button
                      onClick={() => undoPerson(p.id)}
                      className="btn-undo"
                    >
                      Undo
                    </button>
                    <button
                      onClick={() => redoPerson(p.id)}
                      className="btn-redo"
                    >
                      Redo
                    </button>
                    <button
                      onClick={() => viewHistory(p.id)}
                      className="btn-history"
                    >
                      Lịch sử
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* FORM */}
        {showForm && (
          <div className="modal-overlay">
            <div className="modal">
              <h2>{editId ? "Cập nhật nhân viên" : "Thêm nhân viên"}</h2>
              <input
                placeholder="Tên"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <input
                placeholder="Tuổi"
                type="number"
                value={age}
                onChange={(e) => setAge(e.target.value)}
              />
              <div className="modal-actions">
                {editId ? (
                  <button onClick={updatePerson} className="btn-save">
                    Cập nhật
                  </button>
                ) : (
                  <button onClick={addPerson} className="btn-save">
                    Thêm
                  </button>
                )}
                <button onClick={closeForm} className="btn-cancel">
                  Hủy
                </button>
              </div>
            </div>
          </div>
        )}

        {/* LỊCH SỬ */}
        {showHistoryId && (
          <div className="modal-overlay">
            <div className="modal">
              <h3>Lịch sử phiên bản của {showHistoryId}</h3>
              <ul>
                {history.map((h, i) => (
                  <li key={i} className="history">
                    {i + 1}. {h.name} - {h.age}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => setShowHistoryId(null)}
                className="btn-cancel"
              >
                Đóng
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
