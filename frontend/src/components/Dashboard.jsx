import {
  CTable,
  CTableHead,
  CTableRow,
  CTableHeaderCell,
  CTableBody,
  CTableDataCell,
} from "@coreui/react";

//TODO : replace with API call once backend is ready
function Dashboard() {
  return (
    <div className="p-4">
      <h2>Dashboard Table</h2>
      <CTable color="dark" striped>
        <CTableHead>
          <CTableRow>
            <CTableHeaderCell scope="col">Truck ID</CTableHeaderCell>
            <CTableHeaderCell scope="col">Fuel Level</CTableHeaderCell>
            <CTableHeaderCell scope="col">Location</CTableHeaderCell>
            <CTableHeaderCell scope="col">Maintenance</CTableHeaderCell>
            <CTableHeaderCell scope="col">Hours</CTableHeaderCell>
          </CTableRow>
        </CTableHead>
        <CTableBody>
          <CTableRow>
            <CTableHeaderCell scope="row">TRK - 101</CTableHeaderCell>
            <CTableDataCell>50 %</CTableDataCell>
            <CTableDataCell>Manila</CTableDataCell>
            <CTableDataCell>Good</CTableDataCell>
            <CTableDataCell>120 hrs</CTableDataCell>
          </CTableRow>
          <CTableRow>
            <CTableHeaderCell scope="row">TRK - 202</CTableHeaderCell>
            <CTableDataCell>15 %</CTableDataCell>
            <CTableDataCell>Taguig</CTableDataCell>
            <CTableDataCell>Needs to be Checked</CTableDataCell>
            <CTableDataCell>12 hrs</CTableDataCell>
          </CTableRow>
          <CTableRow>
            <CTableHeaderCell scope="row">TRK - 303</CTableHeaderCell>
            <CTableDataCell>66 %</CTableDataCell>
            <CTableDataCell>Pasig</CTableDataCell>
            <CTableDataCell>Bad</CTableDataCell>
            <CTableDataCell>1 hrs</CTableDataCell>
          </CTableRow>
        </CTableBody>
      </CTable>
    </div>
  );
}

export default Dashboard;

