#include "automation.h"
#include "houdini_session.h"
#include "Remotery.h"
#include "stream_writer.h"
#include "types.h"
#include "util.h"

#include <OP/OP_Director.h>
#include <OP/OP_OTLLibrary.h>
#include <GEO/GEO_Primitive.h>
#include <GEO/GEO_IOTranslator.h>
#include <GU/GU_Detail.h>
#include <SOP/SOP_Node.h>
#include <MOT/MOT_Director.h>
#include <UT/UT_Ramp.h>
#include <algorithm>
#include <filesystem>
#include <iostream>

constexpr const char* SOP_NODE_TYPE = "sop";

namespace util
{

static bool can_incremental_cook(const CookRequest& previous, const CookRequest& current)
{
    if (previous.hda_file != current.hda_file)
    {
        return false;
    }

    if (previous.definition_index != current.definition_index)
    {
        return false;
    }

    if (previous.inputs != current.inputs)
    {
        return false;
    }

    if (previous.parameters.size() != current.parameters.size())
    {
        return false;
    }

    auto same_key = [](const auto& entryA, const auto& entryB) { return entryA.first == entryB.first; };
    return std::equal(previous.parameters.begin(), previous.parameters.end(), current.parameters.begin(), same_key);
}

static std::string install_library(MOT_Director* director, const std::string& hda_file, int definition_index, StreamWriter& writer)
{
    // Load the library
    OP_OTLManager& manager = director->getOTLManager();

    int library_index = manager.findLibrary(hda_file.c_str());
    if (library_index < 0)
    {
        manager.installLibrary(hda_file.c_str());

        library_index = manager.findLibrary(hda_file.c_str());
        if (library_index < 0)
        {
            writer.error("Failed to install library: " + hda_file);
            return "";
        }
    }

    // Get the actual library from the index
    OP_OTLLibrary* library = manager.getLibrary(library_index);
    if (!library)
    {
        writer.error("Failed to get library at index " + std::to_string(library_index));
        return "";
    }

    int num_definitions = library->getNumDefinitions();
    if (definition_index >= num_definitions)
    {
        writer.error("Definition index out of range: " + std::to_string(definition_index));
        return "";
    }

    const OP_OTLDefinition& definition = library->getDefinition(definition_index);
    std::string node_type = definition.getName().toStdString();

    size_t first = node_type.find("::");
    if (first != std::string::npos)
    {
        size_t last = node_type.find("::", first + 2);

        if (last != std::string::npos)
        {
            node_type = node_type.substr(first + 2, last - (first + 2));
        }
        else
        {
            node_type = node_type.substr(first + 2);
        }
    }

    return node_type;
}

static OP_Node* create_node(MOT_Director* director, const std::string& node_type, StreamWriter& writer)
{
    // Find the root /obj network
    OP_Network* obj = (OP_Network*)director->findNode("/obj");
    if (!obj)
    {
        writer.error("Failed to find obj network");
        return nullptr;
    }
    assert(obj->getNchildren() == 0 || obj->getNchildren() == 1);

    // Create geo node
    OP_Network* geo = (OP_Network*)obj->findNode("geo");
    if (!geo)
    {
        geo = (OP_Network*)obj->createNode("geo", "geo");
        if (!geo || !geo->runCreateScript())
        {
            writer.error("Failed to create geo node");
            return nullptr;
        }
    }
    assert(geo->getNchildren() == 0);

    // Create the SOP node
    OP_Node* node = geo->createNode(node_type.c_str(), SOP_NODE_TYPE);
    if (!node || !node->runCreateScript())
    {
        writer.error("Failed to create node of type: " + node_type);
        return nullptr;
    }

    return node;
}

static OP_Node* find_node(MOT_Director* director)
{
    // Find the root /obj network
    OP_Network* obj = (OP_Network*)director->findNode("/obj");
    if (!obj)
    {
        return nullptr;
    }
    assert(obj->getNchildren() == 0 || obj->getNchildren() == 1);

    // Find existing geo node
    OP_Network* geo = (OP_Network*)obj->findNode("geo");
    if (!geo)
    {
        return nullptr;
    }

    // Find the existing SOP node
    OP_Node* node = geo->findNode(SOP_NODE_TYPE);
    if (!node)
    {
        return nullptr;
    }

    return node;
}

static OP_Node* create_input_node(OP_Network* parent, const std::string& path, StreamWriter& writer)
{
    if (!std::filesystem::exists(path))
    {
        return nullptr;
    }

    std::string ext = std::filesystem::path(path).extension().string();
    std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);

    if (ext == ".usd" || ext == ".usdz")
    {
        OP_Node* input_node = parent->createNode("usdimport");
        if (!input_node || !input_node->runCreateScript())
        {
            writer.error("Failed to create usdimport node for " + path);
            return nullptr;
        }

        input_node->setString(path.c_str(), CH_STRING_LITERAL, "filepath1", 0, 0.0f);
        input_node->setInt("input_unpack", 0, 0.0f, 1);
        input_node->setInt("unpack_geomtype", 0, 0.0f, 1);
        return input_node;
    }
    else if (ext == ".obj")
    {
        OP_Node* input_node = parent->createNode("obj_importer");
        if (!input_node || !input_node->runCreateScript())
        {
            writer.error("Failed to create obj_importer node for " + path);
            return nullptr;
        }

        input_node->setString(path.c_str(), CH_STRING_LITERAL, "sObjFile", 0, 0.0f);
        return input_node;
    }
    else if (ext == ".fbx")
    {
        OP_Node* input_node = parent->createNode("fbx_archive_import");
        if (!input_node || !input_node->runCreateScript())
        {
            writer.error("Failed to create fbx_archive_import node for " + path);
            return nullptr;
        }

        input_node->setString(path.c_str(), CH_STRING_LITERAL, "sFBXFile", 0, 0.0f);
        input_node->setInt("bConvertUnits", 0, 0.0f, 1);
        input_node->setInt("bImportAnimation", 0, 0.0f, 1);
        input_node->setInt("bImportBoneSkin", 0, 0.0f, 1);
        input_node->setInt("bConvertYUp", 0, 0.0f, 1);
        input_node->setInt("bUnlockGeo", 0, 0.0f, 1);
        input_node->setInt("pack", 0, 0.0f, 1);
        return input_node;
    }
    else if (ext == ".gltf" || ext == ".glb")
    {
        OP_Node* input_node = parent->createNode("gltf");
        if (!input_node || !input_node->runCreateScript())
        {
            writer.error("Failed to create gltf node for " + path);
            return nullptr;
        }

        input_node->setString(path.c_str(), CH_STRING_LITERAL, "filename", 0, 0.0f);
        return input_node;
    }

    return nullptr;
}

static void set_inputs(OP_Node* node, const std::map<int, std::string>& inputs, StreamWriter& writer)
{
    OP_Network* parent = node->getParent();

    for (const auto& [index, path] : inputs)
    {
        OP_Node* input_node = create_input_node(parent, path, writer);
        if (!input_node)
        {
            input_node = parent->createNode("null");
            if (!input_node || !input_node->runCreateScript())
            {
                writer.error("Failed to create null node for " + path);
                continue;
            }
        }

        node->setInput(index, input_node);
    }
}

static void set_parameters(OP_Node* node, const ParameterSet& parameters)
{
    for (const auto& [key, value] : parameters)
    {
        if (std::holds_alternative<int64_t>(value))
        {
            node->setInt(key.c_str(), 0, 0.0f, std::get<int64_t>(value));
        }
        else if (std::holds_alternative<double>(value))
        {
            node->setFloat(key.c_str(), 0, 0.0f, std::get<double>(value));
        }
        else if (std::holds_alternative<std::string>(value))
        {
            node->setString(std::get<std::string>(value).c_str(), CH_STRING_LITERAL, key.c_str(), 0, 0.0f);
        }
        else if (std::holds_alternative<bool>(value))
        {
            node->setInt(key.c_str(), 0, 0.0f, std::get<bool>(value) ? 1 : 0);
        }
        else if (std::holds_alternative<std::vector<int64_t>>(value))
        {
            const auto& int_array = std::get<std::vector<int64_t>>(value);
            for (size_t i = 0; i < int_array.size(); ++i)
            {
                node->setInt(key.c_str(), i, 0.0f, int_array[i]);
            }
        }
        else if (std::holds_alternative<std::vector<double>>(value))
        {
            const auto& float_array = std::get<std::vector<double>>(value);
            for (size_t i = 0; i < float_array.size(); ++i)
            {
                node->setFloat(key.c_str(), i, 0.0f, float_array[i]);
            }
        }
        else if (std::holds_alternative<std::vector<RampPoint>>(value))
        {
            const auto& ramp_points = std::get<std::vector<RampPoint>>(value);

            UT_Ramp ramp;
            for (const auto& point : ramp_points)
            {
                float values[4] = { point.value[0], point.value[1], point.value[2], point.value[3] };
                ramp.addNode(point.position, values, point.basis);
            }

            PRM_Parm* rampParm = node->getParmPtr(key.c_str());
            if (rampParm)
            {
                node->updateMultiParmFromRamp(0.0, ramp, *rampParm, false, PRM_AK_SET_KEY);
            }
        }
    }
}

bool export_geometry_raw(const GU_Detail* gdp, Geometry& geom, StreamWriter& writer)
{
    rmt_ScopedCPUSample(ExportGeometryRaw, 0);

    GA_ROHandleV3 P_handle(gdp, GA_ATTRIB_POINT, "P");
    if (!P_handle.isValid())
    {
        writer.error("Geometry missing point attribute");
        return false;
    }

    GA_ROHandleV3 N_P_handle(gdp, GA_ATTRIB_POINT, "N");
    GA_ROHandleV3 N_V_handle(gdp, GA_ATTRIB_VERTEX, "N");

    GA_ROHandleV3 UV_P_handle(gdp, GA_ATTRIB_POINT, "uv");
    GA_ROHandleV3 UV_V_handle(gdp, GA_ATTRIB_VERTEX, "uv");

    const GEO_Primitive* prim;
    GA_FOR_ALL_PRIMITIVES(gdp, prim)
    {
        if (prim->getTypeId() != GA_PRIMPOLY)
        {
           continue;
        }

        GA_Size num_verts = prim->getVertexCount();
        if (num_verts < 3)
        {
            continue;
        }

        int base_index = geom.points.size() / 3;
        assert(geom.points.size() % 3 == 0);

        for (GA_Size i = 0; i < num_verts; i++)
        {
            GA_Offset ptOff = prim->getPointOffset(i);
            GA_Offset vtxOff = prim->getVertexOffset(i);

            // Position
            UT_Vector3 pos = P_handle.get(ptOff);
            geom.points.push_back(pos.x());
            geom.points.push_back(pos.y());
            geom.points.push_back(pos.z());

            // Normal
            if (N_P_handle.isValid())
            {
                UT_Vector3 norm = N_P_handle.get(ptOff);
                geom.normals.push_back(norm.x());
                geom.normals.push_back(norm.y());
                geom.normals.push_back(norm.z());
            }
            else if (N_V_handle.isValid())
            {
                UT_Vector3 norm = N_V_handle.get(vtxOff);
                geom.normals.push_back(norm.x());
                geom.normals.push_back(norm.y());
                geom.normals.push_back(norm.z());
            }

            // UV
            if (UV_P_handle.isValid())
            {
                UT_Vector3 uv = UV_P_handle.get(ptOff);
                geom.uvs.push_back(uv.x());
                geom.uvs.push_back(uv.y());
            }
            else if (UV_V_handle.isValid())
            {
                UT_Vector3 uv = UV_V_handle.get(vtxOff);
                geom.uvs.push_back(uv.x());
                geom.uvs.push_back(uv.y());
            }
        }

        // Triangulate as a fan
        int num_tris = num_verts - 2;
        for (int i = 0; i < num_tris; i++)
        {
            geom.indices.push_back(base_index + 0);
            geom.indices.push_back(base_index + i + 1);
            geom.indices.push_back(base_index + i + 2);
        }
    }

    if (geom.points.size() == 0)
    {
        writer.error("Geometry contains no primitives");
        return false;
    }

    return true;
}

bool export_geometry_obj(const GU_Detail* gdp, std::vector<char>& file_data, StreamWriter& writer)
{
    rmt_ScopedCPUSample(ExportGeometryOBJ, 0);

    std::unique_ptr<GEO_IOTranslator> xlate(GU_Detail::getSupportedFormat(".obj"));
    if (!xlate)
    {
        writer.error("OBJ export not supported");
        return false;
    }

    std::stringstream buffer;
    GA_Detail::IOStatus status = xlate->fileSave(gdp, buffer);
    if (!status.success())
    {
        writer.error("Failed to export OBJ to buffer");
        return false;
    }

    std::string str = buffer.str();
    file_data.assign(str.begin(), str.end());
    if (file_data.size() == 0)
    {
        writer.error("Empty OBJ file");
        return false;
    }

    return true;
}

bool export_geometry(EOutputFormat format, OP_Node* node, StreamWriter& writer)
{
    rmt_ScopedCPUSample(ExportGeometry, 0);

    SOP_Node* sop = node->castToSOPNode();
    if (!sop)
    {
        writer.error("Node is not a SOP node");
        return false;
    }

    OP_Context context(0.0);
    const GU_Detail* gdp = sop->getCookedGeo(context);
    if (!gdp)
    {
        writer.error("Failed to get cooked geometry");
        return false;
    }

    if (format == EOutputFormat::RAW)
    {
        Geometry geo;
        if (!export_geometry_raw(gdp, geo, writer))
        {
            writer.error("Failed to export raw geometry");
            return false;
        }

        writer.geometry(geo);
    }
    else if (format == EOutputFormat::OBJ)
    {
        std::vector<char> file_data;
        if (!export_geometry_obj(gdp, file_data, writer))
        {
            writer.error("Failed to export obj geometry");
            return false;
        }

        writer.file("generated_model.obj", file_data);
    }
    else
    {
        writer.error("Unknown output format");
        return false;
    }

    return true;
}

void cleanup_session(MOT_Director* director)
{
    rmt_ScopedCPUSample(CleanupSession, 0);

    OP_Network* obj = (OP_Network*)director->findNode("/obj");
    if (obj)
    {
        OP_Network* geo = (OP_Network*)obj->findNode("geo");
        if (geo)
        {
            for (int j = geo->getNchildren() - 1; j >= 0; j--)
            {
                geo->destroyNode(geo->getChild(j));
            }
        }
    }
}

bool cook(HoudiniSession& session, const CookRequest& request, StreamWriter& writer)
{
    rmt_ScopedCPUSample(Cook, 0);

    // Try to re-use an existing node
    OP_Node* node = nullptr;
    {
        rmt_ScopedCPUSample(UpdateScene, 0);
        if (can_incremental_cook(session.m_state, request))
        {
            node = find_node(session.m_director);
            if (!node)
            {
                util::log() << "Failed to find existing node" << std::endl;
            }
        }

        if (!node)
        {
            cleanup_session(session.m_director);
            session.m_state = CookRequest();

            // Install the library
            std::string node_type = install_library(session.m_director, request.hda_file, request.definition_index, writer);
            if (node_type.empty())
            {
                return false;
            }

            // Setup the node
            node = create_node(session.m_director, node_type, writer);
            if (!node)
            {
                return false;
            }

            set_inputs(node, request.inputs, writer);
        }

        set_parameters(node, request.parameters);
        session.m_state = request;
    }

    // Cook the node
    {
        rmt_ScopedCPUSample(CookNode, 0);
        OP_Context context(0.0);
        if (!node->cook(context))
        {
            writer.error("Failed to cook node");
            return false;
        }
    }

    // Export results
    if (!export_geometry(request.format, node, writer))
    {
        writer.error("Failed to export geometry");
        return false;
    }

    return true;
}

}

